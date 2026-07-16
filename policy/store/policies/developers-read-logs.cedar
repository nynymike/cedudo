@id("developers-read-logs")
permit (
    principal,
    action == Linux::Action::"ReadLogs",
    resource == Linux::Service::"cedar-demo"
)
when {
    principal.groups.contains("developers") ||
    principal.groups.contains("operators")
};
