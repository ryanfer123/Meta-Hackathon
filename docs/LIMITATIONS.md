# Limitations and evidence boundaries

- The six public examples are synthetic masks and a manually authored protocol. They establish engineering behavior only. No real-video model accuracy, latency, egress percentage, shadow agreement or successful deployment of Glimmer is claimed.
- Meta account access and physical recordings will be supplied later. Live adapters are validated with mocked transport and the installed SAM parser, not with paid production responses.
- Single camera, fixed tabletop, one protocol per job; 2 fps, at most 180 sampled frames (90 seconds). Fast actions between samples can be missed. Webcam streaming is not implemented.
- Geometry can establish visible contact or placement. It cannot prove liquid transfer, concentration, volume, mixing, sterility, correct cap tightness or hidden actions. This is a non-medical demonstration, not a lab safety system.
- Bbox containment is a coarse geometric approximation; touching thresholds depend on camera resolution. Model confidence is not calibrated. Occluded or ambiguous instances remain unknown.
- Image-keyframe SAM calls do not maintain stable IDs for visually identical objects. Multiple matches produce unknown evidence. Colored props and distinct prompts are required by this adapter. Native-video tracking is exercised by an opt-in spike, not used in the production observer yet.
- Absence/count predicates require complete scene coverage. Live SAM keyframes do not establish coverage, so they cannot confidently certify these predicates. A compiler may propose unusable predicates; validation must reject or repair them.
- All eligible cuts and adjacent inter-group swaps are evaluated. The final-step cut cannot establish a later transition, so its result is explicitly ineligible and finish remains uncertain. Video cuts may retain lasting effects of actions, making a control invalid; failed controls are not hidden.
- Dwell is time since observable activation, including waiting when a step has no preconditions. Define meaningful preconditions or generous dwell bounds for independent steps.
- Rules do not accept model-only completion. Human review is needed for unknown evidence; a confident LLM opinion cannot fill missing pixels.
- Glimmer's Modal deployment is prepared and unexecuted. The GPU image, weight access, cold start, vision and latency still need live verification. Modal is cloud infrastructure, not on-device inference.
- Request and estimated-cost reservations are application guards, not a guarantee against provider charges. Set provider-side controls separately. SAM default call caps may reject long multi-object recordings; increase them deliberately after measuring cost.
- Local files and SQLite target a trusted single-instance deployment. No authentication, multi-tenant isolation, durable distributed queue or production upload gateway is included. Public hosting stays in replay mode.
- Audit verification checks event consistency against a root. Replacing both the chain and root defeats local verification; provenance and external anchoring matter. It does not make the physical observations trustworthy.
- Real dev/test recordings must be independently labelled and frozen. Small samples and correlated events limit any performance conclusion.
