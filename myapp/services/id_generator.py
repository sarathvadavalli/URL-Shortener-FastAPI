"""Base62 IDs are allocated by the database, not by per-process clocks.

The former Snowflake generator was unsafe across instances/workers. Allocation
now happens in URLService's insert/flush transaction via BIGINT AUTO_INCREMENT.
"""
