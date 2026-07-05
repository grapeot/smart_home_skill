# Visual Check Measurement Fixtures

These photorealistic synthetic fixtures demonstrate the measurement-set pattern for LLM-based visual checks. They were generated for the demo and are safe to commit because they contain no real home imagery.

Each fixture pairs an image with ground truth JSON. Unit tests mock the LLM call for deterministic CI, while live evaluations can run the images through LM Studio and compare outputs against the ground truth.

Private deployments should keep real camera measurement sets under ignored paths such as `data/visual_checks/measurement_sets/`.
