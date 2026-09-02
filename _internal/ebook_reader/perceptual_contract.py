from __future__ import annotations


PERCEPTUAL_SHORT_AUDIO_REASON = "PERCEPTUAL_SHORT_AUDIO"
PERCEPTUAL_NATURALNESS_REVIEW_CODE = "PERCEPTUAL_NATURALNESS_REVIEW"
NATURALNESS_REPAIR_ACTION = "generate_immutable_naturalness_candidate_v1"
NATURALNESS_IMPROVEMENT_REQUIREMENT = "naturalness_improvement_v1"
STANDARD_CANDIDATE_GATE_REQUIREMENT = "standard_candidate_gate_v1"

# The register a perceptual score is graded against.
#
# The artifact that gets graded is the raw take: a voice variant is applied on the way into
# the chapter, after every gate. So the reference has to be the preset's own untouched
# preview - matching it to the profile's register would compare raw audio against a
# transformed reference and manufacture a difference that is not there.
#
# It lives here because two places need to agree on it and did not. The pipeline chose it
# deliberately and the database validator compared it against the take's own pitch, so any
# voice carrying a register shift could never satisfy both: seven candidates read by a
# preset at -1 semitone stopped a ten-chapter run twice, at the same line.
PERCEPTUAL_BASELINE_PITCH_SEMITONES = 0
