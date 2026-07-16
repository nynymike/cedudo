@id("forbid-open-shell")
forbid (
    principal,
    action == Linux::Action::"OpenShell",
    resource
);
