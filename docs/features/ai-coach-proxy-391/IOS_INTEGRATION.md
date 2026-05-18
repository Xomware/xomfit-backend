# iOS integration for #391 — AI coach proxy

A follow-up PR in `xomfit-ios` should swap `AICoachService` from calling
Anthropic directly to calling the new backend proxy. The shape is
identical to Anthropic's `/v1/messages` so the change is small.

## Summary

| Before                                          | After                                                            |
|-------------------------------------------------|------------------------------------------------------------------|
| `POST https://api.anthropic.com/v1/messages`    | `POST https://<xomfit-api>/ai-coach/messages`                    |
| Header: `x-api-key: <per-user key>`             | Header: `Authorization: Bearer <Supabase JWT>`                   |
| Header: `anthropic-version: 2023-06-01`         | (removed — proxy adds it server-side)                            |
| `stream: true` SSE                              | `stream: false` JSON (proxy v1)                                  |
| Settings: "Anthropic API Key" field             | Settings: remove field — no longer needed                        |

## Code changes in `Xomfit/Services/AICoachService.swift`

1. Replace the `endpoint` constant:
   ```swift
   // Before:
   private let endpoint = URL(string: "https://api.anthropic.com/v1/messages")!
   // After (point at the backend, env-driven):
   private let endpoint = APIClient.baseURL.appendingPathComponent("ai-coach/messages")
   ```
   Use whatever helper `APIClient` / `BackendConfig` already exposes for the
   xomfit-backend base URL. Do NOT hard-code prod URLs.

2. Replace the auth header:
   ```swift
   // Before:
   request.setValue(apiKey, forHTTPHeaderField: "x-api-key")
   request.setValue(anthropicVersion, forHTTPHeaderField: "anthropic-version")
   // After:
   let jwt = try await SupabaseAuth.shared.currentAccessToken()
   request.setValue("Bearer \(jwt)", forHTTPHeaderField: "Authorization")
   ```

3. Remove the `resolvedAPIKey` / `apiKeyOverride` plumbing. The proxy
   holds the key. Callers should no longer pass a per-user key. Keep the
   function signature for now if it's painful to refactor — just ignore
   the override.

4. Force `stream: false` on the request body (proxy v1 does this server-side
   too, but be explicit so the client doesn't waste time setting up an SSE
   parser path that won't fire):
   ```swift
   let body = AnthropicRequest(
       ...
       stream: false,
       ...
   )
   ```

5. Swap `sendMessageStream` for a non-streaming `sendMessage`. The proxy
   returns the full Anthropic JSON body in one shot — parse it the same
   way the existing SSE path collapses to `.textDelta` / `.toolUse` /
   `.done`, just without the per-line loop.

   ```swift
   func sendMessage(...) async throws -> AICoachResponse {
       let (data, response) = try await session.data(for: request)
       guard let http = response as? HTTPURLResponse,
             (200..<300).contains(http.statusCode) else {
           // 429 special-case: surface the friendly "daily limit" error.
           if (response as? HTTPURLResponse)?.statusCode == 429,
              let body = try? JSONDecoder().decode(ProxyError.self, from: data) {
               throw AICoachServiceError.rateLimited(body.error)
           }
           throw AICoachServiceError.http(...)
       }
       let payload = try JSONDecoder().decode(AnthropicMessageResponse.self, from: data)
       return payload
   }
   ```

6. Add a new error case:
   ```swift
   enum AICoachServiceError: LocalizedError {
       ...
       case rateLimited(String)
   }
   ```

## Settings cleanup

Remove the "Anthropic API Key" row from Settings (and the `@AppStorage`
key it backed). It's now dead. Leave a one-release migration note so any
user who had a key set just stops using it silently.

## Streaming (deferred)

Streaming is intentionally out of scope for v1. When the backend ships
the Lambda Function URL with `RESPONSE_STREAM`, the iOS side can re-enable
the SSE parser path that's currently in `sendMessageStream`. Until then,
the `done` / `textDelta` events from a streamed response can be
synthesized from the full JSON body so the view model code doesn't need
to fork.

## Test plan

- Send a message from a fresh user — first 50/day succeed, 51st returns
  the friendly "Daily message limit reached" error.
- Disable the proxy in DynamoDB IAM and confirm the iOS client surfaces
  a sane error (no crash, no spinner-forever).
- Confirm Settings no longer prompts the user to add an API key.
