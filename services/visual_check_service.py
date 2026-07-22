import asyncio
import base64
import json
import logging
import mimetypes
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import httpx
import jsonschema
import requests
import yaml

from services.camera_service import camera_service

logger = logging.getLogger(__name__)


class VisualCheckError(RuntimeError):
    pass


@dataclass
class Snapshot:
    content: bytes
    mime_type: str
    source: dict[str, Any]


class VisualCheckService:
    def __init__(self, config_path: str = "config/vision_checks.yaml"):
        self.config_path = config_path

    def load_config(self) -> dict[str, Any]:
        config_file = self._resolve_path(self.config_path)
        if not config_file.exists():
            raise VisualCheckError(f"Visual check config not found: {config_file}")
        with open(config_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def list_checks(self) -> list[dict[str, Any]]:
        config = self.load_config()
        checks = config.get("checks", {}) or {}
        return [
            {
                "id": check_id,
                "group": check_config.get("group"),
                "source": check_config.get("source", {}).get("type"),
            }
            for check_id, check_config in checks.items()
        ]

    async def run_check(self, check_id: str, *, save_artifacts: bool = True) -> dict[str, Any]:
        config = self.load_config()
        checks = config.get("checks", {}) or {}
        if check_id not in checks:
            raise VisualCheckError(f"Visual check not found: {check_id}")

        check_config = checks[check_id]
        lmstudio_config = config.get("lmstudio", {}) or {}
        self._ensure_lmstudio(lmstudio_config)

        snapshot = await self._fetch_snapshot(check_config.get("source", {}) or {})
        prompt = self._read_text(check_config["prompt_file"])
        schema = self._read_json(check_config["schema_file"])
        artifact_dir = self._artifact_dir(config, check_id) if save_artifacts else None

        if artifact_dir:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            image_path = artifact_dir / f"snapshot{self._extension_for_mime(snapshot.mime_type)}"
            image_path.write_bytes(snapshot.content)
        else:
            image_path = None

        retries = int(check_config.get("retries", config.get("retries", 1)))
        last_error: Optional[str] = None
        raw_response: Optional[dict[str, Any]] = None
        result_payload: Optional[dict[str, Any]] = None

        for attempt in range(1, retries + 2):
            try:
                raw_response = self._call_lmstudio(
                    lmstudio_config,
                    snapshot,
                    prompt if not last_error else f"{prompt}\n\nPrevious validation error: {last_error}\nReturn only valid JSON matching the schema.",
                    schema,
                )
                result_payload = self._extract_json(raw_response)
                jsonschema.validate(instance=result_payload, schema=schema)
                self._semantic_validate(result_payload)
                last_error = None
                break
            except Exception as exc:
                last_error = str(exc)
                logger.warning("Visual check %s attempt %s failed: %s", check_id, attempt, exc)
                if attempt > retries:
                    break

        assertions = []
        status = "ok"
        if result_payload is None:
            status = "failed"
        else:
            assertions = self._evaluate_assertions(result_payload, check_config.get("assertions", []) or [])
            if any(not item["passed"] for item in assertions):
                status = "problem"

        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        response = {
            "schema_version": "smart_home.visual_check_result.v1",
            "check_id": check_id,
            "status": status,
            "captured_at": now,
            "source": snapshot.source,
            "model": {
                "provider": "lmstudio",
                "api_base": lmstudio_config.get("api_base", "http://127.0.0.1:1234/v1"),
                "model": lmstudio_config.get("model", "qwen/qwen3.5-35b-a3b"),
            },
            "result": result_payload,
            "assertions": assertions,
            "error": last_error,
            "artifacts": {
                "dir": str(artifact_dir) if artifact_dir else None,
                "image_path": str(image_path) if image_path else None,
                "raw_response_path": None,
                "result_path": None,
            },
        }

        if artifact_dir:
            raw_path = artifact_dir / "raw_response.json"
            result_path = artifact_dir / "result.json"
            raw_path.write_text(json.dumps(raw_response, indent=2, ensure_ascii=False), encoding="utf-8")
            result_path.write_text(json.dumps(response, indent=2, ensure_ascii=False), encoding="utf-8")
            response["artifacts"]["raw_response_path"] = str(raw_path)
            response["artifacts"]["result_path"] = str(result_path)

        return response

    async def run_group(self, group: str, *, save_artifacts: bool = True) -> dict[str, Any]:
        checks = [item["id"] for item in self.list_checks() if item.get("group") == group]
        results = []
        for check_id in checks:
            results.append(await self.run_check(check_id, save_artifacts=save_artifacts))
        return {"group": group, "count": len(results), "results": results}

    async def _fetch_snapshot(self, source: dict[str, Any]) -> Snapshot:
        source_type = source.get("type")
        if source_type == "camera_snapshot":
            camera_id = source.get("camera_id")
            if not camera_id:
                raise VisualCheckError("camera_snapshot source requires camera_id")
            content, error = await camera_service.get_snapshot(camera_id)
            if error or content is None:
                raise VisualCheckError(error or f"Could not fetch camera snapshot: {camera_id}")
            return Snapshot(content=content, mime_type="image/jpeg", source={"type": source_type, "camera_id": camera_id})

        if source_type == "http_snapshot":
            url = source.get("url")
            if not url:
                raise VisualCheckError("http_snapshot source requires url")
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
                resp = await client.get(url)
                resp.raise_for_status()
            mime = resp.headers.get("content-type", "image/jpeg").split(";")[0]
            return Snapshot(content=resp.content, mime_type=mime, source={"type": source_type, "url": url})

        raise VisualCheckError(f"Unsupported visual check source type: {source_type}")

    def _call_lmstudio(self, lmstudio_config: dict[str, Any], snapshot: Snapshot, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        image_b64 = base64.b64encode(snapshot.content).decode("ascii")
        api_base = lmstudio_config.get("api_base", "http://127.0.0.1:1234/v1")
        model = lmstudio_config.get("model", "qwen/qwen3.5-35b-a3b")
        timeout = int(lmstudio_config.get("timeout_seconds", 180))
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": [{"type": "text", "text": "You are a careful visual inspection assistant. Return only JSON matching the requested schema."}],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:{snapshot.mime_type};base64,{image_b64}"}},
                        {"type": "text", "text": prompt},
                    ],
                },
            ],
            "temperature": lmstudio_config.get("temperature", 0),
            "max_tokens": int(lmstudio_config.get("max_tokens", 1200)),
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "visual_check", "schema": schema},
            },
        }
        if lmstudio_config.get("chat_template_kwargs") is not None:
            payload["chat_template_kwargs"] = lmstudio_config["chat_template_kwargs"]
        resp = requests.post(f"{api_base.rstrip('/')}/chat/completions", json=payload, timeout=timeout)
        self._raise_for_status(resp)
        return resp.json()

    def _ensure_lmstudio(self, lmstudio_config: dict[str, Any]) -> None:
        api_base = lmstudio_config.get("api_base", "http://127.0.0.1:1234/v1")
        if not self._lmstudio_available(api_base):
            launch = lmstudio_config.get("launch", {}) or {}
            if not launch.get("enabled"):
                raise VisualCheckError(f"LM Studio is not available at {api_base}")
            command = launch.get("command")
            if not command:
                raise VisualCheckError("LM Studio launch is enabled but no command is configured")
            subprocess.Popen(command)
            deadline = time.time() + float(launch.get("wait_seconds", 90))
            while time.time() < deadline:
                if self._lmstudio_available(api_base):
                    break
                time.sleep(3)
            else:
                raise VisualCheckError(f"LM Studio did not become available at {api_base}")

        self._ensure_lmstudio_model(lmstudio_config)

    def _ensure_lmstudio_model(self, lmstudio_config: dict[str, Any]) -> None:
        api_base = lmstudio_config.get("api_base", "http://127.0.0.1:1234/v1")
        native_base = api_base.rstrip("/")
        if native_base.endswith("/v1"):
            native_base = native_base[:-3]
        model = lmstudio_config.get("model", "qwen/qwen3.5-35b-a3b")
        timeout = int(lmstudio_config.get("timeout_seconds", 180))

        models_response = requests.get(f"{native_base}/api/v1/models", timeout=5)
        self._raise_for_status(models_response)
        models = models_response.json().get("models", [])
        if any(item.get("key") == model and item.get("loaded_instances") for item in models):
            return

        payload: dict[str, Any] = {"model": model}
        if lmstudio_config.get("context_length") is not None:
            payload["context_length"] = int(lmstudio_config["context_length"])
        load_response = requests.post(f"{native_base}/api/v1/models/load", json=payload, timeout=timeout)
        self._raise_for_status(load_response)

    def _raise_for_status(self, response: requests.Response) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = response.text.strip()
            if detail:
                raise VisualCheckError(f"{exc}; response: {detail[:2000]}") from exc
            raise

    def _lmstudio_available(self, api_base: str) -> bool:
        try:
            resp = requests.get(f"{api_base.rstrip('/')}/models", timeout=5)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def _extract_json(self, raw_response: dict[str, Any]) -> dict[str, Any]:
        message = raw_response["choices"][0]["message"]
        content = message.get("content") or message.get("reasoning_content") or ""
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        return self._parse_json_object(content)

    def _parse_json_object(self, text: str) -> dict[str, Any]:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            start = stripped.find("{")
            end = stripped.rfind("}")
            if start >= 0 and end > start:
                return json.loads(stripped[start : end + 1])
            raise

    def _semantic_validate(self, payload: dict[str, Any]) -> None:
        overall = payload.get("overall")
        if isinstance(overall, dict):
            doors = payload.get("garage_doors") or payload.get("doors") or []
            cars = payload.get("cars") or []
            if "door_count" in overall and doors and overall["door_count"] != len(doors):
                raise VisualCheckError("overall.door_count does not match visible door records")
            if "car_count" in overall and cars and overall["car_count"] != len(cars):
                raise VisualCheckError("overall.car_count does not match visible car records")

    def _evaluate_assertions(self, payload: dict[str, Any], assertions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results = []
        for assertion in assertions:
            path = assertion.get("path")
            expected = assertion.get("equals")
            actual = self._lookup_path(payload, path or "")
            results.append(
                {
                    "name": assertion.get("name", path),
                    "path": path,
                    "expected": expected,
                    "actual": actual,
                    "passed": actual == expected,
                }
            )
        return results

    def _lookup_path(self, payload: dict[str, Any], path: str) -> Any:
        if not path.startswith("$."):
            raise VisualCheckError(f"Unsupported assertion path: {path}")
        current: Any = payload
        for part in path[2:].split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current

    def _read_text(self, path: str) -> str:
        return self._resolve_path(path).read_text(encoding="utf-8")

    def _read_json(self, path: str) -> dict[str, Any]:
        return json.loads(self._resolve_path(path).read_text(encoding="utf-8"))

    def _resolve_path(self, path: str) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return Path(__file__).parent.parent / candidate

    def _artifact_dir(self, config: dict[str, Any], check_id: str) -> Path:
        root = config.get("artifact_dir", "data/visual_checks")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self._resolve_path(root) / check_id / timestamp

    def _extension_for_mime(self, mime_type: str) -> str:
        if mime_type == "image/jpeg":
            return ".jpg"
        return mimetypes.guess_extension(mime_type) or ".img"


visual_check_service = VisualCheckService(os.getenv("VISUAL_CHECK_CONFIG", "config/vision_checks.yaml"))
