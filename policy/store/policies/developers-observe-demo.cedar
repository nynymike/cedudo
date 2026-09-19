@id("developers-observe-demo")
permit (
    principal is Linux::User,
    action == Linux::Action::"read-logs",
    resource == Linux::Service::"cedar-demo"
)
when {
    principal has groups &&
    (principal.groups.contains("developers") ||
     principal.groups.contains("operators"))
};
