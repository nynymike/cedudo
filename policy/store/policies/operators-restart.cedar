@id("operators-restart")
permit (
    principal is Linux::User,
    action == Linux::Action::"restart",
    resource
)
when {
    principal has groups &&
    principal.groups.contains("operators") &&
    context has intruder_risk_level &&
    context.intruder_risk_level == "low"
};
