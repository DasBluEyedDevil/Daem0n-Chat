# Phase 2: User Profiles & Multi-User - Context

**Gathered:** 2026-02-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Each user has an isolated, persistent profile that stores and recalls personal facts about them. Multiple users can share a device with Claude knowing household relationships but keeping individual memories private.

</domain>

<decisions>
## Implementation Decisions

### User Identification
- Project path identifies the household/device, not the individual user
- Default user is assumed on session start — Claude greets by name
- If user says "this isn't [Name]", Claude apologizes and performs introduction flow for new/returning user
- If conversation patterns feel "off" (different topics, tone, timing), Claude can gently verify identity
- Unlimited users per device/project path — no artificial cap

### Profile Storage
- Profiles stored as memories with a 'profile' category (unified with memory system, not separate table)
- Hybrid structure: name and core identity are structured, preferences/traits flow as tagged memories
- Core identity (name, key relationships) is permanent — never decays
- Preferences and style notes can evolve and decay like other memories

### Multi-User Isolation
- Shared household context: users are isolated but Claude knows they share a device
- Claude can light cross-reference ("this came up with Susan too") but never shares specifics
- Each user's profile is completely private — no admin role, no viewing other profiles
- Household relationships are modeled in the knowledge graph (Steve and Susan are partners)

### Profile Bootstrapping
- Friendly introduction when Claude meets a new user
- Claude introduces himself as Claude but offers to go by a different name (stored per-user)
- Light profile building: 3 natural questions woven into conversation (not an interview)
- Tone: playful and casual — put the user at ease

### Claude's Discretion
- Exact wording of introduction and onboarding questions
- How to detect "conversation feels off" patterns
- How to phrase light cross-references without feeling creepy
- Knowledge graph relationship types and modeling

</decisions>

<specifics>
## Specific Ideas

- Greeting by name at session start serves dual purpose: personalization AND identity verification (user can correct if wrong)
- The Steve/Susan exchange is a perfect example: "Actually this isn't Susan, it's Steve" → apology → "nice to meet you Steve" → conversational onboarding
- Per-user nickname for Claude ("I'd like to call you [X]") adds intimacy without complexity

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-user-profiles-multi-user*
*Context gathered: 2026-02-07*
