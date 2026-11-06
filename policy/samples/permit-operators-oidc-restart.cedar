// Permit operators to restart only if they authenticated via OIDC/authd.
// auth_method is an ADVISORY signal, so it is paired with group membership
// rather than used as the only condition.
@id("permit-operators-oidc-restart")
permit (
    principal is Linux::User,
    action == Linux::Action::"restart",
    resource
)
when {
    principal has groups &&
    principal.groups.contains("operators") &&
    context has auth_method &&
    context.auth_method == "oidc"
};
