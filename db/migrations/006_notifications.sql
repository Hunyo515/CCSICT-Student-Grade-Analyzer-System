--------------------------------------------------------------------------
-- Migration 006 — Notifications (topbar bell, all 3 portals)
-- Run this if you already executed db/schema.sql. Fresh installs can just
-- use the updated db/schema.sql directly (this migration is folded into it).
--------------------------------------------------------------------------

CREATE TABLE notifications (
    notification_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         NUMBER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    message         VARCHAR2(255) NOT NULL,
    link            VARCHAR2(255),
    is_read         VARCHAR2(1) DEFAULT 'N' CHECK (is_read IN ('Y', 'N')),
    created_at      TIMESTAMP DEFAULT SYSTIMESTAMP
);

CREATE INDEX idx_notif_user_unread ON notifications(user_id, is_read);

COMMIT;
