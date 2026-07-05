Inspect this garage camera snapshot.

Return only JSON matching the configured schema. Identify visible cars and visible garage doors. Use stable bay labels from the image when configured by the local deployment, and use `unknown` when a detail is not visible enough to classify.

For garage doors, state must be one of `open`, `closed`, or `uncertain`. Do not mark a door closed unless the full opening appears blocked by the door. Do not mark a door open unless daylight/outdoor space or a raised panel is visible.
