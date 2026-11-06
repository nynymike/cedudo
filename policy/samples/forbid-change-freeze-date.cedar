// Change freeze: block all restarts on specific calendar dates (US Central).
// Uses the ISO date string; extend the set with additional freeze dates.
@id("forbid-change-freeze-date")
forbid (
    principal,
    action == Linux::Action::"restart",
    resource
)
when {
    context has date &&
    ["2026-12-24", "2026-12-25", "2026-12-31"].contains(context.date)
};
