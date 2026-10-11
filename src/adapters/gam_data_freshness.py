"""When Google Ad Manager's reported figures for a period are expected complete.

GAM has no "period finalised" signal, so this module uses a heuristic based on:
1. Report metadata (date ranges in response)
2. Known GAM processing delays (4 hours)
3. The daily ready hour, 7 AM ET (4 AM PT), an hour after GAM's 3 AM PT freeze

The GAM adapter reports the answer as ``expected_availability`` beside the figures it has, and
never refuses a read on it; each caller decides what an unfinished period means for it.
"""

import logging
from datetime import UTC, datetime, time, timedelta

import pytz

logger = logging.getLogger(__name__)


class GAMDataFreshnessValidator:
    """When GAM's reported figures for a period are expected complete."""

    # Known GAM processing delays
    STANDARD_DELAY_HOURS = 4
    DAILY_DATA_READY_HOUR_ET = 7  # 7 AM ET = 4 AM PT (1 hour after freeze)

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
    def expected_availability(cls, reporting_data, target_date: datetime, *, now: datetime) -> datetime | None:
        """When the heuristic expects GAM's figures through *target_date* complete.

        Args:
            reporting_data: ReportingData from GAMReportingService
            target_date: The end of the period the figures are for (timezone-aware)
            now: The current time (timezone-aware)

        Returns:
            None when the heuristic holds the figures complete. Otherwise the
            timezone-aware time (US Eastern) it expects them complete, never earlier than
            *now*: a caller that polls should look again then.
        """
        tz = pytz.timezone("America/New_York")
        now = now.astimezone(tz)
        ready = time(cls.DAILY_DATA_READY_HOUR_ET, 5)
        # A day's figures are complete from DAILY_DATA_READY_HOUR_ET the next morning;
        # GAMReportingService._calculate_data_validity reads the same constant. The target is read
        # as a date in the data's time zone. If that time is already past and GAM is still behind,
        # the next such morning (today's if the clock has not passed it) is the earliest the
        # heuristic can say the figures are complete.
        available_at = tz.localize(datetime.combine(target_date.astimezone(tz).date() + timedelta(days=1), ready))
        if available_at < now:
            day = now.date() if now.time() <= ready else now.date() + timedelta(days=1)
            available_at = tz.localize(datetime.combine(day, ready))

        # Check 1: Is it too early in the day for yesterday's data? This also covers the previous
        # month's figures: GAM freezes them at 03:00 PT on the 1st, before DAILY_DATA_READY_HOUR_ET.
        if now.hour < cls.DAILY_DATA_READY_HOUR_ET:
            logger.debug("Too early for complete data (hour %s, need %s+)", now.hour, cls.DAILY_DATA_READY_HOUR_ET)
            return available_at

        # Check 2: Is the data valid until after our target date? This also covers a report that
        # ends before the target: GAMReportingService ends every report now, and data_valid_until
        # is never later than that.
        if reporting_data.data_valid_until.date() < target_date.date():
            logger.debug(
                "Data only valid until %s, need %s", reporting_data.data_valid_until.date(), target_date.date()
            )
            return available_at

        return None
