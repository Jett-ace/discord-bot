# Configurable chest award probabilities and upgrade chains.
# Tweak these values to adjust reward rates across dispatches and games.

EXPLORE = {
    # chance to double all chest drops in high-tier singularities
    "maybe_double_chance": 0.20,
    # Orleans: chance to spawn an exquisite instead of common
    "orleans_exquisite_chance": 0.20,
    # Mid-tier Singularities thresholds: cumulative probabilities for luxurious / precious / exquisite
    # Example: r < lux_threshold -> lux, elif r < precious_threshold -> precious, elif r < exquisite_threshold -> exquisite, else common
    "mid_lux_threshold": 0.10,
    "mid_precious_threshold": 0.40,
    "mid_exquisite_threshold": 0.70,
    "mid_double_chance": 0.20,
    # High-tier (Camelot/Babylonia): extra lux chance and double chance
    "high_lux_chance": 0.40,
    "high_double_chance": 0.20,
    # Extra fate chance per luxurious chest (additional to guaranteed 1 fate)
    "lux_extra_fate_chance": 0.20,
}

RPS = {
    # RPS chest upgrade/double chain
    "initial_double": 0.60,            # initial 60% chance to add a second common
    "common_to_exquisite": 0.80,
    "exquisite_double": 0.30,
    "exquisite_to_precious": 0.40,
    "precious_double": 0.20,
    "precious_to_luxurious": 0.20,
    "luxurious_double": 0.05,
}

# Export convenience
DEFAULTS = {
    "EXPLORE": EXPLORE,
    "RPS": RPS,
}
