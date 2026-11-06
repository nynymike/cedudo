// Block restarts whenever the threat posture is above "low". cedudo sends
// intruder_risk_level="low" today; this policy is ready for when a higher
// level is introduced.
@id("forbid-restart-elevated-risk")
forbid (
    principal,
    action == Linux::Action::"restart",
    resource
)
when {
    context has intruder_risk_level &&
    context.intruder_risk_level != "low"
};
