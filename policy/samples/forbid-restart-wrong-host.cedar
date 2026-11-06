// Pin restart authority to a specific host. On any other host, restarts are
// blocked outright. Useful when one policy store is shared across machines.
@id("forbid-restart-wrong-host")
forbid (
    principal,
    action == Linux::Action::"restart",
    resource
)
when {
    context has hostname &&
    context.hostname != "workshop-vm"
};
