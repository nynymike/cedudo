@id("developers-read-logs")
permit (
    principal is Linux::User,
    action == Linux::Action::"ReadLogs",
    resource == Linux::Service::"cedar-demo"
)
when {
    principal has groups &&
    (principal.groups.contains("developers") ||
     principal.groups.contains("operators"))
};
