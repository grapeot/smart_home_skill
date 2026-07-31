from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class FlexibleModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApiError(FlexibleModel):
    detail: str


class HealthResponse(FlexibleModel):
    status: str = Field(..., description="Service health status")


class HueStatus(FlexibleModel):
    name: Optional[str] = None
    is_on: Optional[bool] = None
    brightness: Optional[int] = None
    timer_active: Optional[bool] = None
    error: Optional[str] = None


class ActionResult(FlexibleModel):
    status: Optional[str] = Field(None, description="Action result status, usually success or error")
    message: Optional[str] = None


class WemoDeviceStatus(FlexibleModel):
    name: Optional[str] = None
    is_on: Optional[bool] = None
    host: Optional[str] = None
    port: Optional[int] = None
    error: Optional[str] = None


class SamsungTVStatus(FlexibleModel):
    configured: Optional[bool] = None
    is_on: Optional[bool] = None
    volume: Optional[int] = None
    muted: Optional[bool] = None
    error: Optional[str] = None


class RoonNowPlaying(FlexibleModel):
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None


class RoonOutput(FlexibleModel):
    output_id: Optional[str] = None
    display_name: Optional[str] = None


class RoonZone(FlexibleModel):
    zone_id: Optional[str] = None
    display_name: Optional[str] = None
    state: Optional[str] = None
    now_playing: Optional[RoonNowPlaying] = None
    outputs: List[RoonOutput] = Field(default_factory=list)


class RoonStatus(FlexibleModel):
    configured: Optional[bool] = None
    authorized: Optional[bool] = None
    connected: Optional[bool] = None
    core_name: Optional[str] = None
    core_id: Optional[str] = None
    host: Optional[str] = None
    zone_count: Optional[int] = None
    zones: Optional[List[RoonZone]] = None
    pair: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class RoonZonesResponse(FlexibleModel):
    status: Optional[str] = None
    zones: List[RoonZone] = Field(default_factory=list)
    message: Optional[str] = None


class RoonPairStatus(FlexibleModel):
    status: Optional[str] = None
    message: Optional[str] = None
    authorized: Optional[bool] = None
    display_name: Optional[str] = None
    core_name: Optional[str] = None
    core_id: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None



class RinnaiStatus(FlexibleModel):
    device_id: Optional[str] = None
    is_online: Optional[bool] = None
    set_temperature: Optional[int] = None
    inlet_temp: Optional[int] = None
    outlet_temp: Optional[int] = None
    water_flow: Optional[int] = None
    recirculation_enabled: Optional[bool] = None
    error: Optional[str] = None


class GarageStatus(FlexibleModel):
    door_count: int
    available: bool
    doors: Optional[List[Dict[str, Any]]] = None


class RingSensorStatus(FlexibleModel):
    name: Optional[str] = None
    device_type: Optional[str] = None
    category_id: Optional[int] = None
    faulted: Optional[bool] = None
    derived_state: Optional[str] = None
    tamper_status: Optional[str] = None
    comm_status: Optional[str] = None
    battery_level: Optional[int] = None
    battery_status: Optional[str] = None
    last_update: Optional[Any] = None
    last_comm_time: Optional[Any] = None


class RingLocationStatus(FlexibleModel):
    name: Optional[str] = None
    has_hubs: Optional[bool] = None
    has_alarm_base_station: Optional[bool] = None
    devices: List[RingSensorStatus] = Field(default_factory=list)


class RingStatusResponse(FlexibleModel):
    schema_version: Optional[str] = None
    source: Optional[str] = None
    observed_at: Optional[str] = None
    locations: List[RingLocationStatus] = Field(default_factory=list)
    updated_refresh_token_available: Optional[bool] = None
    configured: bool = True
    error: Optional[str] = None


class NotificationResult(FlexibleModel):
    enabled: Optional[bool] = None
    sent: Optional[bool] = None
    recipients: Optional[int] = None
    resend_id: Optional[str] = None
    reason: Optional[str] = None
    error: Optional[str] = None


class GarageToggleResponse(ActionResult):
    door: Optional[int] = None
    action: Optional[str] = None
    backend: Optional[str] = None
    previous_state: Optional[Dict[str, Any]] = None
    target_open: Optional[bool] = None
    reported_state: Optional[Any] = None
    final_state: Optional[Dict[str, Any]] = None
    verified: Optional[bool] = None
    executed: Optional[int] = None
    timestamp: Optional[str] = None
    notification: Optional[NotificationResult] = None


class AllStatusResponse(FlexibleModel):
    hue: Optional[HueStatus] = None
    wemo: Optional[Dict[str, WemoDeviceStatus]] = None
    rinnai: Optional[RinnaiStatus] = None
    garage: Optional[GarageStatus] = None
    ring: Optional[RingStatusResponse] = None
    samsung: Optional[SamsungTVStatus] = None
    roon: Optional[RoonStatus] = None


class HistoryRecord(FlexibleModel):
    id: Optional[int] = None
    device_type: str
    device_name: str
    timestamp: str
    data: Dict[str, Any]


class CameraInfo(FlexibleModel):
    id: str
    name: str


class CameraListResponse(FlexibleModel):
    cameras: List[CameraInfo]


class VisualCheckListResponse(FlexibleModel):
    checks: List[Dict[str, Any]]


class VisualCheckRunResponse(FlexibleModel):
    schema_version: Optional[str] = None
    check_id: Optional[str] = None
    status: Optional[str] = None
    captured_at: Optional[str] = None
    source: Optional[Dict[str, Any]] = None
    model: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    assertions: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None
    artifacts: Optional[Dict[str, Any]] = None
    group: Optional[str] = None
    count: Optional[int] = None
    results: Optional[List[Dict[str, Any]]] = None


class EmptyActionParams(StrictModel):
    pass


class HueOnParams(StrictModel):
    brightness: int = Field(128, ge=1, le=254)


class DeviceActionParams(StrictModel):
    device: str = Field(..., min_length=1)


class RinnaiCirculateParams(StrictModel):
    duration: int = Field(5, gt=0, le=60)


class GarageToggleParams(StrictModel):
    door: int = Field(..., ge=1)


class HueToggleAction(StrictModel):
    type: Literal["hue.toggle"]
    params: EmptyActionParams = Field(default_factory=EmptyActionParams)


class HueOnAction(StrictModel):
    type: Literal["hue.on"]
    params: HueOnParams = Field(default_factory=HueOnParams)


class HueOffAction(StrictModel):
    type: Literal["hue.off"]
    params: EmptyActionParams = Field(default_factory=EmptyActionParams)


class WemoToggleAction(StrictModel):
    type: Literal["wemo.toggle"]
    params: DeviceActionParams


class WemoOnAction(StrictModel):
    type: Literal["wemo.on"]
    params: DeviceActionParams


class WemoOffAction(StrictModel):
    type: Literal["wemo.off"]
    params: DeviceActionParams


class RinnaiCirculateAction(StrictModel):
    type: Literal["rinnai.circulate"]
    params: RinnaiCirculateParams = Field(default_factory=RinnaiCirculateParams)


class GarageToggleAction(StrictModel):
    type: Literal["garage.toggle"]
    params: GarageToggleParams


class RoonZoneParams(StrictModel):
    zone: str = Field(..., min_length=1)


class RoonPlayParams(StrictModel):
    zone: str = Field(..., min_length=1)
    source: Literal["queue", "playlist"] = "queue"
    playlist: Optional[str] = None


class RoonPlayAction(StrictModel):
    type: Literal["roon.play"]
    params: RoonPlayParams


class RoonPauseAction(StrictModel):
    type: Literal["roon.pause"]
    params: RoonZoneParams


class RoonStopAction(StrictModel):
    type: Literal["roon.stop"]
    params: RoonZoneParams


ScheduleAction = Annotated[
    Union[
        HueToggleAction,
        HueOnAction,
        HueOffAction,
        WemoToggleAction,
        WemoOnAction,
        WemoOffAction,
        RinnaiCirculateAction,
        GarageToggleAction,
        RoonPlayAction,
        RoonPauseAction,
        RoonStopAction,
    ],
    Field(discriminator="type"),
]


class CreateActionRequest(FlexibleModel):
    minutes: float = Field(..., gt=0, le=1440, description="Delay before execution, in minutes")
    action: ScheduleAction


class ScheduledActionResponse(FlexibleModel):
    id: str
    action: Optional[Dict[str, Any]] = None
    action_display: Optional[str] = None
    minutes: Optional[float] = None
    created_at: Optional[str] = None
    execute_at: Optional[str] = None
    status: str


class ScheduledActionListResponse(FlexibleModel):
    actions: List[ScheduledActionResponse]


DeviceKind = Literal["hue", "wemo", "rinnai", "garage", "ring"]
