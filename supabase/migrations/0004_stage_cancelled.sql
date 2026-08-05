-- V2 repost tasks skip the source acquisition stages atomically.
alter type stage_status add value if not exists 'cancelled';
