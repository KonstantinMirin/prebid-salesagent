"""When Google Ad Manager's reported figures for a period are expected complete.

GAM has no "period finalised" signal, so this module uses a heuristic based on:
1. Report metadata (date ranges in response)
2. Known GAM processing delays (4 hours)
3. Documented freeze times (3 AM PT for monthly data)

The GAM adapter reports the answer as ``expected_availability`` beside the figures it has, and
never refuses a read on it; each caller decides what an unfinished period means for it.
"""

import logging
from datetime import UTC, datetime, time, timedelta

import pytz
from pytz.tzinfo import BaseTzInfo

logger = logging.getLogger(__name__)


class GAMDataFreshnessValidator:
    """When GAM's reported figures for a period are expected complete."""

    # Known GAM processing delays
    STANDARD_DELAY_HOURS = 4
    DAILY_DATA_READY_HOUR_ET = 7  # 7 AM ET = 4 AM PT (1 hour after freeze)
    MONTHLY_FREEZE_HOUR_PT = 3  # 3 AM PT on 1st of month

    @classmethod
    def get_freshness_timestamp(cls, reporting_data) -> dict:
        """Get metadata about data freshness for webhook payload.

        Returns:
            Dict with freshness metadata to include in webhook
        """
        return {
            "data_valid_until": reporting_data.data_valid_until.isoformat(),
            "data_timezone": reporting_data.data_timezone,
            "report_end_date": reporting_data.end_date.isoformat(),
            "query_type": reporting_data.query_type,
            "freshness_checked_at": datetime.now(UTC).isoformat(),
        }

    @classmethod
    def expected_availability(
        cls,
        reporting_data,
        target_date: datetime,
        *,
        now: datetime,
        timezone: str = "America/New_York",
    ) -> datetime | None:
        """When the heuristic expects GAM's figures through *target_date* complete.

        Args:
            reporting_data: ReportingData from GAMReportingService
            target_date: The end of the period the figures are for (timezone-aware)
            now: The current time (timezone-aware)
            timezone: Timezone for calculations

        Returns:
            None when the heuristic holds the figures complete. Otherwise the
            timezone-aware time it expects them complete, never earlier than *now*: a
            caller that polls should look again then.
        """
        tz = pytz.timezone(timezone)
        now = now.astimezone(tz)
        ready = time(cls.DAILY_DATA_READY_HOUR_ET, 5)
        # A day's figures are complete from DAILY_DATA_READY_HOUR_ET the next morning, the rule
        # GAMReportingService._calculate_data_validity applies. The target is read as a date in
        # the data's time zone. If that time is already past and GAM is still behind, the next
        # such morning is the earliest the heuristic can say the figures are complete.
        available_at = tz.localize(datetime.combine(target_date.astimezone(tz).date() + timedelta(days=1), ready))
        if available_at < now:
            available_at = cls._next_wall_time(now, tz, ready)

        # Check 1: Is it too early in the day for yesterday's data?
        if now.hour < cls.DAILY_DATA_READY_HOUR_ET:
            logger.debug("Too early for complete data (hour %s, need %s+)", now.hour, cls.DAILY_DATA_READY_HOUR_ET)
            return available_at

        # Check 2: Does the report actually include our target date?
        if reporting_data.end_date.date() < target_date.date():
            logger.debug(
                "Report ends %s, figures needed through %s", reporting_data.end_date.date(), target_date.date()
            )
            return available_at

        # Check 3: Is the data valid until after our target date?
        if reporting_data.data_valid_until.date() < target_date.date():
            logger.debug(
                "Data only valid until %s, need %s", reporting_data.data_valid_until.date(), target_date.date()
            )
            return available_at

        # Check 4: Is this month-end data that might still be processing?
        if target_date.day == 1 and target_date.month != (target_date - timedelta(days=1)).month:
            # First day of new month - previous month might still be processing
            pt_tz = pytz.timezone("America/Los_Angeles")
            if now.astimezone(pt_tz).hour < cls.MONTHLY_FREEZE_HOUR_PT:
                logger.debug("Month-end data still processing (freeze at %s PT)", cls.MONTHLY_FREEZE_HOUR_PT)
                return cls._next_wall_time(now, pt_tz, time(cls.MONTHLY_FREEZE_HOUR_PT + 1, 5)).astimezone(tz)

        return None

    @staticmethod
    def _next_wall_time(now: datetime, tz: BaseTzInfo, at: time) -> datetime:
        """The first moment not before *now* at which the clock in *tz* reads *at*."""
        local = now.astimezone(tz)
        day = local.date() if local.time() <= at else local.date() + timedelta(days=1)
        return tz.localize(datetime.combine(day, at))
