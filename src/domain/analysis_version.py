# Version of the analysis engine: extraction rules, legal checks, practice comparison.
# Bump when a change must invalidate saved analyses: a message whose stored
# ``engine_version`` differs from this constant is marked ``stale`` and offered
# for recalculation (T43). Old analyses without the field are stale too.
ANALYSIS_VERSION = "analysis/1"
