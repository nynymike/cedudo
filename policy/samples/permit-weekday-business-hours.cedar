// Permit operators to restart services on weekdays during business hours
// (Monday-Friday, 09:00-16:59 US Central). Combines day_of_week and hour.
@id("permit-weekday-business-hours")
permit (
    principal is Linux::User,
    action == Linux::Action::"restart",
    resource
)
when {
    principal has groups &&
    principal.groups.contains("operators") &&
    context.day_of_week >= 1 && context.day_of_week <= 5 &&
    context.hour >= 9 && context.hour < 17
};
