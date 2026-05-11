# Considerations

## Storage vs. Accuracy (Route Simplification)
MotoTwist uses the Ramer-Douglas-Peucker algorithm to simplify route geometries before saving them to the database. Because standard OSRM routes contain thousands of redundant coordinate points on straightaways, simplification drastically reduces database storage and read API response times (does not affect write response times).

You can configure the simplification tolerance in your `.env` file via `TWIST_SIMPLIFICATION_TOLERANCE_M`. Below is a guide to help you choose the right tier for your server capabilities:

-   **`0m` (Raw OSRM Data):**
    No simplification. This preserves the exact OSRM output but consumes massive amounts of database storage and will result in enormous API payloads when clients request to view routes. Not recommended for public instances.

-   **`1m - 3m` (High Fidelity):**
    Ideal for track-day enthusiasts who want mathematically perfect geometry. It trims the worst of the bloat while preserving every micro-curve. Long routes will still consume significant database space.

-   **`5m` (The Default / Sweet Spot):**
    The recommended setting. Based on performance testing, a 5 metre tolerance reduces route data weight by **50% to 80%** while maintaining **>99.5% accuracy** on total route length, even on highly twisty mountain passes.

-   **`15m - 30m` (Storage Saver):**
    Recommended for self-hosters running the app on very constrained hardware (e.g., a 1GB VPS). Tight hairpins will begin to look visually "clipped" on the map, and total route length calculations may underreport by **1% to 3%**.

-   **`30m+` (Danger Zone):**
    At this level, the algorithm aggressively flattens geometries. Short, intricate features like roundabouts and cul-de-sacs will be completely destroyed and rendered as straight lines. Use with extreme caution.


## Tuning the Sorting Algorithm
MotoTwist uses a Bayesian sorting algorithm to ensure that highly-rated Twists with very few rides don't unfairly dominate the top of the list. Instead of just looking at the raw average, MotoTwist weighs a Twists's overall average against the global average and the total volume of rides.

You can tune this behavior using two variables in your `.env` file:

1.  **`INSIGNIFICANT_RIDE_COUNT_PERCENTILE`**:
    Before MotoTwist fully trusts a Twist's rating, it needs to prove itself by accumulating enough rides. This variable sets that threshold by looking at the bottom percentile of your instance's ride counts.
    * If a Twist is below the threshold, its rating is pulled heavily toward the global average.
    * If a Twist is above the threshold, the algorithm trusts the its actual rating.

2.  **`HIDDEN_GEM_AVERAGE_MULTIPLIER`**:
    The "Hidden Gems" sort explicitly looks for Twists that are below the above threshold but are highly rated. This multiplier defines what "highly rated" means by comparing it to the global average rating. At the `1.25` default, a Twist must be 25% better than the global average to be considered a gem.
