# Example of a finding at the right depth

### Version number comes from the caller, not the locked row
- Location: persistence/observations.py:75-95 (commit_correction); caller: pipeline/ingest.py:210
- Problem: commit_correction locks the prior row with SELECT ... FOR UPDATE but then computes the new version from a `prior_version_number` argument that the caller read before the lock was taken. If another worker corrected the same observation in between, the argument is stale and the insert writes a duplicate or wrong version. The function also never checks that the locked row is still current.
- Principle: race condition (check-then-act), trusting stale input
- Fix: read version_number and is_current from the locked row; raise a specific StaleCorrection exception if the row is no longer current; remove the parameter.
- Effort: S

# What a bad finding looks like (never write these)
- "The code could be more modular and follow SOLID better."
- "Consider using the Factory pattern."
- "Error handling should be improved."
Why they are bad: no location, no failure scenario, no concrete fix, and the pattern solves no problem found in the code.
