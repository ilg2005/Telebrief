"""
Core digest generation function.
"""

import logging
from datetime import datetime
from typing import Optional

from src.collector import MessageCollector
from src.config_loader import Config
from src.formatter import DigestFormatter
from src.sender import DigestSender
from src.summarizer import Summarizer


async def generate_digest(config: Config, logger: logging.Logger, hours: int = 24) -> str:
    """
    Core digest generation function.
    Used by both scheduler and bot commands.

    Args:
        config: Application configuration
        logger: Logger instance
        hours: Lookback period in hours

    Returns:
        Formatted digest string

    Raises:
        Exception: If digest generation fails
    """
    start_time = datetime.utcnow()
    logger.info(f"{'=' * 60}")
    logger.info(f"Starting digest generation for last {hours} hours")
    logger.info(f"{'=' * 60}")

    try:
        # Step 1: Collect messages
        logger.info("STEP 1: Collecting messages from Telegram")
        collector = MessageCollector(config, logger)

        await collector.connect()
        try:
            messages_by_channel = await collector.fetch_messages(hours=hours)
        finally:
            await collector.disconnect()

        total_messages = sum(len(msgs) for msgs in messages_by_channel.values())
        logger.info(f"Collected {total_messages} messages from {len(messages_by_channel)} channels")

        # Step 2: Generate summaries
        logger.info("STEP 2: Generating AI summaries")
        summarizer = Summarizer(config, logger)
        summary_result = await summarizer.summarize_all(messages_by_channel)

        channel_summaries = summary_result["channel_summaries"]
        overview = summary_result["overview"]

        logger.info(f"Generated summaries for {len(channel_summaries)} channels")
        logger.debug(f"Overview length: {len(overview) if overview else 0} chars")
        logger.debug(f"Overview content: {overview[:200] if overview else 'EMPTY'}")
        for ch_name, ch_summary in channel_summaries.items():
            logger.debug(
                f"Channel '{ch_name}' summary length: {len(ch_summary) if ch_summary else 0} chars"
            )
            logger.debug(
                f"Channel '{ch_name}' summary: {ch_summary[:200] if ch_summary else 'EMPTY'}"
            )

        # Step 3: Format digest
        logger.info("STEP 3: Formatting digest")
        formatter = DigestFormatter(config, logger)
        digest = formatter.create_digest(
            overview=overview,
            channel_summaries=channel_summaries,
            messages_by_channel=messages_by_channel,
            period_display=f"последние {hours} часов",
        )

        # Calculate execution time
        execution_time = (datetime.utcnow() - start_time).total_seconds()

        logger.info(f"{'=' * 60}")
        logger.info(f"✅ Digest generation completed in {execution_time:.1f}s")
        logger.info(f"{'=' * 60}")

        return digest

    except Exception as e:
        logger.error(f"❌ Digest generation failed: {e}", exc_info=True)
        raise


async def generate_and_send_digest(
    config: Config, logger: logging.Logger, hours: int = 24, user_id: Optional[int] = None
) -> bool:
    """
    Generate and send digest.

    Args:
        config: Application configuration
        logger: Logger instance
        hours: Lookback period
        user_id: Target user ID

    Returns:
        True if successful
    """
    try:
        # Generate digest
        digest = await generate_digest(config, logger, hours)

        # Send digest
        logger.info("STEP 4: Sending digest")
        sender = DigestSender(config, logger)
        success = await sender.send_digest(digest, user_id)

        return success

    except Exception as e:
        logger.error(f"Failed to generate and send digest: {e}")
        return False


async def generate_and_send_channel_digests(
    config: Config, logger: logging.Logger, hours: int = 24, user_id: Optional[int] = None
) -> bool:
    """
    Generate and send separate digest messages for each channel.

    Args:
        config: Application configuration
        logger: Logger instance
        hours: Lookback period
        user_id: Target user ID

    Returns:
        True if successful
    """
    start_time = datetime.utcnow()
    logger.info(f"{'=' * 60}")
    logger.info(f"Starting per-channel digest generation for last {hours} hours")
    logger.info(f"{'=' * 60}")

    try:
        # Step 1: Collect messages
        logger.info("STEP 1: Collecting messages from Telegram")
        collector = MessageCollector(config, logger)

        await collector.connect()
        try:
            messages_by_channel = await collector.fetch_messages(hours=hours)
        finally:
            await collector.disconnect()

        total_messages = sum(len(msgs) for msgs in messages_by_channel.values())
        logger.info(f"Collected {total_messages} messages from {len(messages_by_channel)} channels")

        if total_messages == 0:
            logger.warning("No messages collected, skipping digest generation")
            return False

        # Step 2: Generate summaries
        logger.info("STEP 2: Generating AI summaries")
        summarizer = Summarizer(config, logger)
        summary_result = await summarizer.summarize_all(messages_by_channel)

        channel_summaries = summary_result["channel_summaries"]
        logger.info(f"Generated summaries for {len(channel_summaries)} channels")

        # Step 3: Format individual channel messages
        logger.info("STEP 3: Formatting individual channel messages")
        formatter = DigestFormatter(config, logger)
        channel_messages = []

        for channel_name, summary in channel_summaries.items():
            # Skip empty summaries or errors
            if not summary or "ошибка" in summary.lower():
                logger.warning(f"Skipping channel '{channel_name}': empty or error summary")
                continue

            # Get messages for this channel
            messages = messages_by_channel.get(channel_name, [])

            # Format message
            formatted_message = formatter.format_channel_message(
                channel_name=channel_name,
                summary=summary,
                messages=messages,
                period_display=f"последние {hours} часов",
            )

            channel_messages.append((channel_name, formatted_message))
            logger.info(f"Formatted message for {channel_name}: {len(formatted_message)} chars")

        if not channel_messages:
            logger.warning("No valid channel messages to send")
            return False

        # Step 4: Cleanup old digests (if enabled)
        sender = DigestSender(config, logger)
        if config.settings.auto_cleanup_old_digests:
            logger.info("STEP 4: Cleaning up old digest messages")
            await sender.cleanup_old_digests(user_id)

        # Step 5: Send channel messages with tracking
        logger.info(f"STEP 5: Sending {len(channel_messages)} channel messages")
        summary_message = formatter.format_summary_message(
            total_channels=len(channel_messages),
            total_messages=total_messages,
            period_display=f"последние {hours} часов",
        )
        success = await sender.send_channel_messages_with_tracking(
            channel_messages, summary_message, user_id
        )

        # Calculate execution time
        execution_time = (datetime.utcnow() - start_time).total_seconds()

        logger.info(f"{'=' * 60}")
        logger.info(f"✅ Per-channel digest generation completed in {execution_time:.1f}s")
        logger.info(f"{'=' * 60}")

        return success

    except Exception as e:
        logger.error(f"❌ Per-channel digest generation failed: {e}", exc_info=True)
        return False


async def generate_history_digest(
    config: Config,
    logger: logging.Logger,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    user_id: Optional[int] = None,
    period_display: str = "История канала",
    target_channel_id: Optional[int] = None,
) -> bool:
    """
    Generate digest for a specific history period.

    Args:
        config: Application configuration
        logger: Logger instance
        start_date: Start date
        end_date: End date
        user_id: Target user ID
        period_display: Text description of the period
        target_channel_id: ID of specific channel to analyze

    Returns:
        True if successful
    """
    start_time = datetime.utcnow()
    logger.info(f"{'=' * 60}")
    logger.info(f"Starting history digest generation: {period_display}")
    if target_channel_id:
        logger.info(f"Target Channel ID: {target_channel_id}")
    logger.info(f"{'=' * 60}")

    try:
        # Step 1: Collect messages
        logger.info("STEP 1: Collecting messages from Telegram")
        collector = MessageCollector(config, logger)

        await collector.connect()
        try:
            messages_by_channel = await collector.fetch_messages(
                hours=0,
                start_date=start_date,
                end_date=end_date,
                target_channel_id=target_channel_id,
            )
        finally:
            await collector.disconnect()

        total_messages = sum(len(msgs) for msgs in messages_by_channel.values())
        logger.info(
            f"Collected {total_messages} messages from {len(messages_by_channel)} channels"
        )

        if total_messages == 0:
            logger.warning("No messages collected, skipping digest generation")
            return False

        # Step 2: Generate summaries (using history prompt)
        logger.info("STEP 2: Generating AI summaries (History Mode)")
        summarizer = Summarizer(config, logger)
        summary_result = await summarizer.summarize_all(
            messages_by_channel, use_history_prompt=True
        )

        channel_summaries = summary_result["channel_summaries"]
        logger.info(f"Generated summaries for {len(channel_summaries)} channels")

        # Step 3: Format individual channel messages
        logger.info("STEP 3: Formatting individual channel messages")
        formatter = DigestFormatter(config, logger)
        channel_messages = []

        for channel_name, summary in channel_summaries.items():
            # Skip empty summaries or errors
            if not summary or "ошибка" in summary.lower():
                logger.warning(f"Skipping channel '{channel_name}': empty or error summary")
                continue

            # Get messages for this channel
            messages = messages_by_channel.get(channel_name, [])

            # Format message
            formatted_message = formatter.format_channel_message(
                channel_name=channel_name,
                summary=summary,
                messages=messages,
                period_display=period_display,
            )

            channel_messages.append((channel_name, formatted_message))
            logger.info(f"Formatted message for {channel_name}: {len(formatted_message)} chars")

        if not channel_messages:
            logger.warning("No valid channel messages to send")
            return False

        # Step 4: Send channel messages (without cleanup of daily digests)
        logger.info(f"STEP 4: Sending {len(channel_messages)} channel messages")
        sender = DigestSender(config, logger)
        
        summary_message = formatter.format_summary_message(
            total_channels=len(channel_messages),
            total_messages=total_messages,
            period_display=period_display,
        )
        
        # We don't use send_channel_messages_with_tracking because that saves message IDs for cleanup
        # For history, we probably just want to send them and NOT mark them for daily cleanup.
        # But maybe we want to be able to cleanup history digests too?
        # For now, let's just send them using sender.bot.send_message directly or add a new method in sender?
        # Actually, DigestSender methods are focused on daily digest.
        # Let's use send_channel_messages_with_tracking but maybe we should NOT save IDs if we don't want cleanup?
        # But the user might want to clean up manually later.
        # Let's just use the same method, it's fine if they get mixed or we can add a flag to not save IDs.
        # The prompt didn't specify cleanup behavior for history. I'll stick to standard behavior.
        
        success = await sender.send_channel_messages_with_tracking(
            channel_messages, summary_message, user_id
        )

        # Calculate execution time
        execution_time = (datetime.utcnow() - start_time).total_seconds()

        logger.info(f"{'=' * 60}")
        logger.info(f"✅ History digest generation completed in {execution_time:.1f}s")
        logger.info(f"{'=' * 60}")

        return success

    except Exception as e:
        logger.error(f"❌ History digest generation failed: {e}", exc_info=True)
        return False
