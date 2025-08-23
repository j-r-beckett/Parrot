from pydantic import BaseModel


class Directions(BaseModel):
    """Schema for Valhalla directions response"""

    steps: list[str]  # List of instruction strings
    total_time: str  # Formatted as "n hours, m minutes" or "m minutes"
    total_distance: str  # Total distance in miles

    @classmethod
    def from_valhalla_response(cls, trip: dict) -> "Directions":
        """Create Directions from Valhalla API response"""
        steps = []

        # Process each maneuver in the legs
        for leg in trip.get("legs", []):
            for maneuver in leg.get("maneuvers", []):
                # Combine instruction with verbal_post_transition_instruction
                instruction = maneuver.get("instruction", "")
                verbal_post = maneuver.get("verbal_post_transition_instruction", "")
                if verbal_post:
                    full_instruction = f"{instruction} {verbal_post}"
                else:
                    full_instruction = instruction

                steps.append(full_instruction)

        # Get total time and distance from summary
        summary = trip.get("summary", {})
        total_time_seconds = summary.get("time", 0)
        total_time_formatted = cls._format_time(total_time_seconds)
        total_distance = summary.get("length", 0)

        return cls(
            steps=steps,
            total_time=total_time_formatted,
            total_distance=f"{total_distance} miles",
        )

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds into 'n hours, m minutes' or 'm minutes'"""
        total_minutes = int(seconds / 60)
        hours = total_minutes // 60
        minutes = total_minutes % 60

        if hours > 0:
            if minutes > 0:
                return f"{hours} hours, {minutes} minutes"
            else:
                return f"{hours} hours"
        else:
            return f"{minutes} minutes"