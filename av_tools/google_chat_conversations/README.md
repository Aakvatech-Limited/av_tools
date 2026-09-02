# Google Chat Conversations

Mirrors Frappe `Notification Log` records to Google Chat.

## Delivery modes

### Personal Threaded Space (recommended)

Creates one private named Google Chat space per ERPNext user and adds only that user. Notifications linked to an ERPNext document use a deterministic `thread.threadKey`, so subsequent notifications for the same document remain in the same Chat thread.

Google Chat app direct messages are flat conversations and don't support threaded replies. Use this mode when thread-per-document behavior is required.

### Direct Message

Sends the notification to the existing direct message between the Chat app and the user. This mode is private but unthreaded. `Google Chat User.google_chat_user_id` must contain the immutable Google user ID; app-authenticated `spaces.findDirectMessage` doesn't accept an email alias.

## Setup

1. Create/configure a Google Chat app in the Google Cloud project.
2. Enable the Google Chat API.
3. Create a service account for the integration.
4. Have the Google Workspace administrator approve the app-auth scopes used by this integration:
   - `https://www.googleapis.com/auth/chat.bot`
   - `https://www.googleapis.com/auth/chat.app.spaces.create`
   - `https://www.googleapis.com/auth/chat.app.memberships`
5. Run `bench --site <site> migrate` after installing/updating `av_tools`.
6. Open **Google Chat Settings** in ERPNext.
7. Paste the complete service-account credential JSON into **Service Account JSON**.
8. Keep **Personal Threaded Space** selected for thread-per-document delivery.
9. Enable the integration.

`Google Chat User` records are created lazily from `Notification Log.for_user`. The ERPNext user's email is used as the Google Workspace email by default and can be overridden in the mapping record.

## Processing model

`Notification Log.after_insert` queues delivery with `enqueue_after_commit=True`. The worker:

1. Resolves/creates `Google Chat User`.
2. Resolves/creates the user's delivery space.
3. For linked documents, resolves/creates `Google Chat Conversation` using site + user + DocType + document name.
4. Converts the Notification Log HTML subject to plain text.
5. Sends the Chat message with an idempotent request ID.
6. Stores Google space/thread/message resource names in conversation and delivery records.

`Google Chat Delivery Log` has a unique link to `Notification Log`, preventing normal duplicate processing. Google's request ID provides API-level idempotency for retries of the same notification.

## Thread identity

The external thread key is a SHA-256 hash of:

`site | document_type | document_name`

The internal conversation key additionally contains the ERPNext user. This means the same ERPNext document can have separate private conversations for different recipients without collisions.

## Security

The service-account JSON is stored in a Frappe `Password` field. Only System Managers can manage the integration DocTypes. Do not store service-account credentials in source control or site configuration committed to Git.
