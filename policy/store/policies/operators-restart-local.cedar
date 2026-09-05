@id("operators-restart-local")
permit (
    principal is Linux::User,
    action == Linux::Action::"Restart",
    resource == Linux::Service::"cedar-demo"
)
when {
    principal has groups &&
    principal.groups.contains("operators") 
};
