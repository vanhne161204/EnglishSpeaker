# 01 PRD

## 1. Product Name

EnglishTalker

## 2. Product Summary

EnglishTalker is an app for people who want to practice speaking English.

The app helps users find other people to talk with. Users can join a room, match with one person, or get a random match. Users can choose a normal mode or an incognito mode. The app also has AI assistance to suggest better sentences and help users improve while they are speaking.

The main goal is simple: help users speak English more often, with less fear, and with better support.

## 3. Problem Statement

Many English learners know grammar and vocabulary, but they do not speak often.

Common problems are:

- Users are afraid of making mistakes.
- Users do not know what topic to talk about.
- Users do not have speaking partners.
- Users feel shy when speaking with strangers.
- Users do not know how to improve their sentences.
- Users may forget useful sentences after a conversation.

EnglishTalker solves this by giving users speaking rooms, matching tools, useful topics, sentence notes, and real-time AI help.

## 4. Product Vision

The vision is to create a safe and easy place where people can practice English speaking every day.

The app should make English practice feel simple. A user should be able to open the app, choose a topic, find a partner, and start talking quickly.

The app should also help users learn from each conversation. Users should not only speak, but also get better over time.

## 5. Target Users

The main users are English learners who want more speaking practice.

Target users include:

- Students who want to improve speaking skills.
- Workers who need English for their job.
- Job seekers who want to practice interview English.
- Beginners who want simple conversation practice.
- Intermediate learners who want to speak more naturally.
- People who feel shy and need a safer way to practice.

The first version should focus on beginner and intermediate users.

## 6. Main User Goals

Users want to:

- Practice speaking English with real people.
- Find people with a similar English level.
- Talk about clear topics.
- Get help when they do not know what to say.
- Improve their sentence before or during speaking.
- Save useful sentences for later review.
- Practice without showing too much personal information if they feel shy.

## 7. Product Modes

The app has two speaking modes.

### 7.1 Normal Mode

Normal mode is for users who are comfortable showing their normal profile.

In normal mode:

- The user can show their name or public profile name.
- The user can show their level and interests.
- Other users may see basic profile information.
- The user can join rooms or matches with other normal mode users.

### 7.2 Incognito Mode

Incognito mode is for users who want more privacy.

In incognito mode:

- The user can practice without showing their real identity.
- The app can show a temporary display name.
- The user can still choose level, interests, and topic.
- The user can only match with users who are also in incognito mode.

Important rule:

- Normal mode users should only match with normal mode users.
- Incognito mode users should only match with incognito mode users.

This rule helps users feel safe and respected.

## 8. Core Features

## 8.1 Topics

Topics are conversation subjects that users can talk about.

Examples:

- Daily life
- Travel
- Food
- Work
- School
- Job interview
- Hobbies
- Technology
- Culture

Topics are created and managed by the admin.

The admin should be able to:

- Add a new topic.
- Edit a topic.
- Remove a topic.
- Set topic level, such as beginner, intermediate, or advanced.
- Add sample questions for each topic.

Users should be able to:

- View available topics.
- Choose a topic before joining a room or match.
- See simple conversation questions for the selected topic.

## 8.2 Documentation Content

Documentation content means learning content added by the admin.

This content can include:

- Topic explanations
- Example sentences
- Useful vocabulary
- Common mistakes
- Speaking tips
- Sample answers

The admin adds this content so the AI can give better help.

Simple explanation:

- The admin gives trusted content to the app.
- The AI uses this content when helping users.
- This makes AI suggestions more useful and more related to the topic.

This is called RAG in technical design, but for normal users it means:

The AI looks at trusted learning material before giving suggestions.

## 8.3 Rooms

A room is a place where people can join and make a conversation.

A room can have:

- A topic
- A level
- A mode
- A list of users
- A conversation area
- AI support

Users should be able to:

- View available rooms.
- Join a room.
- Leave a room.
- Speak or chat with other people in the room.
- Use AI assistance during the conversation.

Room rules:

- A room has one mode: normal or incognito.
- Only users with the same mode can join the room.
- A room can have a topic.
- A room can have a suggested level.
- Users should see room information before joining.

One room model:

- A group room and a 1-on-1 conversation are the same model.
- A 1-on-1 is simply a room that seats two people.
- Each room has a kind, either "group" or "1-on-1", so the app can use one code path for both.
- Users can filter the room list by All, Group, or 1-on-1.
- Every room, group or 1-on-1, has the same features, including the in-room translator (see 8.10).

Real-time text chat:

- Inside a room, users talk by sending text messages in real time.
- Messages appear instantly for everyone in the room.
- The app keeps a history of messages so a user who joins can read what was said.
- In incognito rooms, each user is shown a temporary name instead of their real name.

Voice calls:

- Inside a room, users can join a live voice call and talk to each other by speaking, which is the most natural way to practice English.
- Audio is sent directly between users (peer-to-peer), so the server only helps users find and connect to each other.
- Voice works best for a 1-on-1 room or a small group. Larger rooms will need a media server later.
- Because real-time voice needs device features (microphone and speaker), the app must run in a secure context (HTTPS, or `localhost` in development) to use voice.

Microphone control:

- Each user has a microphone toggle for the room. When the microphone is on, the user's voice is sent to the other members. When it is off (muted), the user can still hear others but is not heard.
- The user should always be able to see whether their microphone is on or off.
- A user can leave the voice call while staying in the room (still reading and sending text chat).

Speaker control:

- Each user has a speaker toggle for the room. When the speaker is on, the user hears the other members. When it is off, the user is muted for listening — the user's own microphone state does not change.
- This lets a user silence the room quickly (for example, when in a noisy place) without leaving the call.

Team member audio:

- Every other member in the room appears in the member list with a live speaking or muted indicator, so a user can see who is talking and who is muted.
- Each remote member's audio plays independently, so turning the speaker off silences all remote members at once.

Room owner controls:

- The user who creates a room is its owner (host). Rooms created by the system have no owner.
- The owner can mute a member (turn their microphone off) so the member is not heard, and turn it back on, to keep the conversation orderly.
- The owner can remove (kick) a member from the room if needed, for example for bad behaviour.
- A removed member is told they were removed and is returned to the room list; they cannot rejoin the same room.
- These controls appear only to the owner, next to each member in the member list. A normal member does not see them and cannot moderate others.
- Muting a member is a request the member's app follows. Enforcement is cooperative in this version; a media server would enforce it strictly later.

## 8.4 Match One

Match One means matching one user with one other user.

This is for users who prefer a private 1-on-1 conversation.

A Match One result is a 1-on-1 room. It uses the same room model as a group room (see 8.3), only with the kind set to 1-on-1 and a capacity of two.

The app should match users by:

- Same mode
- Same or similar topic
- Same or similar interest
- Same or close English level

Example:

A beginner user in incognito mode wants to talk about travel. The app should try to find another beginner or near-beginner user in incognito mode who also wants to talk about travel or has travel as an interest.

## 8.5 Random Match

Random Match helps users start faster.

The user clicks random match, and the app finds a room or one person for them.

Random match must still follow important rules:

- The matched users must have the same mode.
- The app should prefer the same or similar topic.
- The app should prefer similar interests.
- The app should prefer a similar English level.

If there is no perfect match, the app can choose the closest match.

The app should tell the user if the match is not exact.

Example:

"We could not find the same topic, but we found a user with the same level."

## 8.6 Match Conditions

The app should use these conditions when matching users:

### Mode

Mode is required.

Users can only match with users in the same mode.

### Topic

Topic is important.

Users should be matched with people who want to talk about the same topic when possible.

### Interest

Interest helps users enjoy the conversation.

Examples of interests:

- Movies
- Music
- Travel
- Business
- Games
- Sports
- Study
- Technology

### Level

Level helps users feel comfortable.

Example levels:

- Beginner
- Elementary
- Intermediate
- Upper intermediate
- Advanced

The app should avoid matching a very new beginner with a very advanced speaker unless both users accept it.

## 8.7 Sentence Note

Sentence Note lets users save useful sentences.

Users should be able to save:

- A sentence they said
- A better sentence suggested by AI
- A useful sentence from another user
- A topic question
- A phrase they want to remember

Users should be able to:

- Add a sentence note.
- Edit a sentence note.
- Delete a sentence note.
- Review sentence notes later.
- Group sentence notes by topic.

Example:

Original sentence:

"I very like travel."

Improved sentence:

"I really like traveling."

The user can save the improved sentence as a note.

## 8.8 AI Assistance

AI Assistance helps users during the conversation.

The AI should be simple, helpful, and not embarrassing.

AI can help users by:

- Suggesting what to say next.
- Improving a sentence.
- Correcting grammar.
- Making a sentence sound more natural.
- Giving topic questions.
- Explaining vocabulary.
- Giving short examples.
- Helping when the user does not know how to answer.

AI should work in real time or near real time.

This means the user can get help while the conversation is happening, not only after the conversation ends.

### In-Room AI Coach

Inside a room the user has a small AI coach with two quick actions:

- Improve my sentence: the user types a sentence and the coach rewrites it to sound more natural and correct, in a gentle and encouraging way.
- Idea: the coach suggests a short, natural thing the user could say next, based on the last message.

The user can tap to use a suggestion (it fills the message box) or save it to their sentence notes. Users can also long-press any message to save it to notes. This keeps help and review in one place and lowers the fear of making mistakes.

### Chatting With AI

The user can talk to the AI coach in two ways:

- By text: the user types a message to the AI and reads the reply. This is the coach described above.
- By voice: the user speaks to the AI and the AI answers, so the user can practice a spoken conversation even when no other member is available.

Both ways use the same AI help. Voice is added on top so the practice feels closer to a real conversation.

### Voice With AI

Voice With AI lets the user have a spoken practice conversation with the AI coach inside the room.

How it works:

- The user starts Voice With AI and speaks a sentence or question.
- The app changes the speech into text (Speech-to-Text) so the user can see what they said.
- The AI replies with a short, helpful answer, and the app can read the answer aloud so the user hears natural English.
- The user can save any AI sentence to their sentence notes.

Important rule — do not mix the two audio sources:

- The room microphone (for talking to other members) and Voice With AI must not be active at the same time.
- When the user starts talking to the AI by voice, the app automatically turns off the room microphone, so the other members do not hear the user's private practice with the AI.
- When the user finishes talking to the AI, the app turns the room microphone back on to the state it was in before (if it was on before, it returns to on; if it was off, it stays off).
- This keeps the user's AI practice private and prevents the AI conversation from disturbing the rest of the room.

### AI With Trusted Content

The AI should use admin-provided documents when giving help.

Simple example:

If the topic is "Job Interview", the admin can add interview questions, sample answers, and useful vocabulary. Then the AI can use that content to suggest better interview answers.

This keeps the AI focused on the selected topic.

### AI Suggestion Rules

The AI should:

- Use simple and clear English.
- Give short suggestions first.
- Avoid making users feel bad.
- Explain mistakes politely.
- Give examples when useful.
- Stay related to the topic.
- Avoid unsafe or offensive content.

## 8.9 Speech-to-Text

Speech-to-Text means the app changes spoken words into written text.

Each conversation should support Speech-to-Text when users speak.

This helps users because they can:

- See what they said as text.
- Review the  conversation after speaking.
- Save useful sentences more easily.
- Let AI understand the conversation better.
- Get better sentence improvement from AI.
- Notice speaking mistakes moreclearly.

Speech-to-Text should work in rooms and Match One conversations.

For Random Match, Speech-to-Text should also work after the user joins a room or a one-to-one match.

### Conversation Transcript

A conversation transcript is the written version of the conversation.

The app should create a transcript for each conversation when Speech-to-Text is turned on.

Users should be able to:

- See their spoken words as text.
- Save useful sentences from the transcript.
- Use the transcript for AI feedback.
- Review the transcript after the conversation if allowed by the app.

### Speech-to-Text Rules

The app should follow these rules:

- Users should know when Speech-to-Text is active.
- Users should be able to understand that their voice is being changed into text.
- The transcript should be used to help learning.
- The app should protect user privacy.
- Incognito conversations should be handled carefully.
- If Speech-to-Text makes a mistake, the user should still be able to continue the conversation.

Speech-to-Text does not need to be perfect in the first version. It should be good enough to help users review and improve their speaking.

## 8.10 In-Room Translator

The in-room translator lets a user translate a word or phrase without leaving the conversation.

While speaking in a room, a user often hears an English word they do not understand, or wants to say something but does not know the English words. Instead of opening another app such as Google Translate, the user can translate directly inside the room interface.

How it works:

- The translator is part of the room screen, next to the conversation.
- The user types a word or short phrase.
- The translation appears instantly while the user is typing.
- The user does not need to press a separate button.

Language direction:

- By default, the user translates from English to their own language (for example, English to Vietnamese) to understand a word they just heard.
- The user can swap the direction with one tap to translate from their own language to English when they do not know how to say something.

Why this matters:

- It removes the need to leave the app during a conversation.
- It helps users keep talking instead of stopping to search for a word.
- It lowers the fear of getting stuck on one unknown word.

Translator rules:

- The translator works in both group rooms and 1-on-1 rooms, because they are the same room model.
- The translator should be fast and feel instant.
- The translation engine is Google Translate by default, which gives the most accurate Vietnamese meaning. It is not a large language model. An offline open-source engine (Argos Translate) is also available for private, no-network use. If the engine is not available, the app shows a clear demo result instead of failing.
- Translation is a helper tool. It should not replace the user's effort to speak English.

## 8.11 Subscription

Subscription is the way the app can offer free and paid plans.

The app should have a free plan so new users can start practicing without payment. The app can also have a paid plan for users who want more practice and more AI help.

The subscription should be simple and easy to understand.

### Free Plan

The free plan is for new users and casual learners.

Free users can:

- Create an account.
- Set their level and interests.
- Join basic rooms.
- Use Match One with limits.
- Use Random Match with limits.
- Save sentence notes with limits.
- Use a limited number of AI suggestions per day.

### Premium Plan

The premium plan is for users who want more speaking practice and more learning support.

Premium users can:

- Use more AI suggestions.
- Save more sentence notes.
- Access more topics.
- Get better AI feedback after conversations.
- Use more Match One sessions.
- Join premium rooms if the app supports them later.
- See more progress information.

### Subscription Rules

The app should follow these rules:

- Users should always know what is free and what is paid.
- The app should not stop users suddenly during a conversation because of payment.
- If a user reaches a free limit, the app should explain the limit in simple words.
- Users should be able to see their current plan.
- Users should be able to upgrade when they want.
- Users should be able to cancel the subscription when they want.

Payment details can be handled in the Business Requirement Document and Deployment document later.

## 8.12 Warm-up Practice

Warm-up Practice is a solo mode that helps a user get ready to speak before they
join a room or a match. It lowers the fear of speaking by letting the user
practice alone first, with no other people watching.

Warm-up is a guided, one-person chat. It looks like a chat box:

- The user opens Warm-up from the menu and chooses a topic.
- The system shows one question about that topic at a time, like a message in the chat.
- The user answers by turning on the microphone and speaking.
- The app changes the spoken answer into text (Speech-to-Text) and shows the answer as a message in the chat, so the user can see what they said.
- After the user answers, the system shows the next question, and the user answers again. The practice goes step by step, one question per turn.

Warm-up rules:

- Questions come from the chosen topic and match the topic's level when possible.
- The user should be able to see the transcript of every answer they gave.
- The user should be able to save any answer to their sentence notes.
- If speech is not available or a word is wrong, the user can still type the answer, so the practice never gets stuck.
- Warm-up is single-user. It does not connect to other members and does not use the room voice call.
- When the user finishes the questions, the app shows a short summary and invites the user to join a room or a match to keep practicing with people.

Why this matters:

- The user can warm up their speaking before talking to a real person.
- The user practices topic questions they will likely meet in a room.
- Seeing the transcript builds confidence and makes it easy to save good sentences.

## 9. User Types

### Lightweight Profile

A new user starts by creating a lightweight profile: a display name, an English
level, and interests. There is no password in this version — the profile is saved
on the device so the user is remembered next time. This keeps the first step fast
and removes a barrier to start practicing. A full account with login can be added
later without changing this idea.

## 9.1 Normal User

A normal user is a person who uses the app to practice English.

Normal users can:

- Create an account.
- Set their English level.
- Set their interests.
- View their subscription plan.
- Choose normal mode or incognito mode.
- Join rooms.
- Use Match One.
- Use Random Match.
- Use AI assistance.
- Use Speech-to-Text during conversations.
- Save sentence notes.
- Review old notes.

## 9.2 Admin

An admin manages the learning content and app structure.

Admins can:

- Create topics.
- Edit topics.
- Delete topics.
- Add documentation content.
- Edit documentation content.
- Manage room rules.
- Review reported content or users.
- Keep the app safe and useful.

## 10. Main User Journey

## 10.1 First-Time User Journey

1. User opens the app.
2. User creates an account or logs in.
3. User chooses English level.
4. User chooses interests.
5. User chooses normal mode or incognito mode.
6. User chooses a topic.
7. User joins a room, uses Match One, or uses Random Match.
8. User starts speaking with another user.
9. Speech-to-Text changes spoken words into text.
10. User uses AI help when needed.
11. User saves useful sentences.
12. User reviews notes after the conversation.

## 10.2 Returning User Journey

1. User opens the app.
2. User sees suggested topics or rooms.
3. User can open Warm-up to practice topic questions alone before joining others.
4. User starts a new conversation quickly.
4. Speech-to-Text creates a text version of the conversation.
5. User gets AI suggestions during the conversation.
6. User saves new sentences.
7. User checks progress over time.

## 11. MVP Scope

MVP means the first simple version of the product.

The first version should include the most important features only.

## 11.1 Must-Have Features

The MVP must include:

- User account.
- User profile with English level and interests.
- Normal mode.
- Incognito mode.
- Admin topic management.
- Admin documentation content management.
- Basic subscription plan display.
- Basic usage limits for free users.
- Room list.
- Join room.
- Leave room.
- In-room voice call between members with microphone on/off and speaker on/off controls.
- Voice With AI (spoken practice with the AI coach) that mutes the room microphone while active.
- Match One.
- Random Match.
- Match by same mode.
- Match by topic, interest, and level when possible.
- Sentence note.
- In-room translator with instant translation.
- Speech-to-Text for conversations.
- Basic conversation transcript.
- AI sentence suggestion.
- AI sentence improvement.
- AI topic-based help using admin content.

## 11.2 Should-Have Features

These features are useful but can come after the first version if needed:

- Warm-up practice (solo guided topic questions with Speech-to-Text).
- Conversation history.
- User progress page.
- Favorite topics.
- Report user.
- Block user.
- Room owner moderation (mute, unmute, or remove a member).
- Basic user rating after conversation.
- AI feedback after the conversation.
- Subscription upgrade flow.
- Subscription cancellation flow.

## 11.3 Out Of Scope For MVP

These features are not required in the first version:

- Payment system.
- Complex payment promotion system.
- Teacher dashboard.
- Mobile app.
- Video call.
- Advanced pronunciation scoring.
- Certificate.
- Large social network features.
- Public posts or news feed.

## 12. Product Rules

The app should follow these rules:

- Users in normal mode only match with normal mode users.
- Users in incognito mode only match with incognito mode users.
- Users should know the topic before joining a room or match.
- The app should try to match users by topic first.
- The app should use interests to improve match quality.
- The app should use English level to keep conversations comfortable.
- Speech-to-Text should be available for conversations when voice is used.
- Users should know when Speech-to-Text is active.
- AI suggestions should be helpful, short, and polite.
- Admin content should guide AI answers.
- A group room and a 1-on-1 room are the same model, separated only by room kind.
- Users can turn their room microphone on or off, and their room speaker on or off, at any time during a voice call.
- The room owner (the user who created the room) can mute, unmute, or remove a member; only the owner sees these controls, and a removed member cannot rejoin the same room.
- Users should always know whether their microphone and speaker are on or off.
- The room microphone and Voice With AI must never be active at the same time. Starting Voice With AI turns the room microphone off; finishing Voice With AI restores it to its previous state.
- Users should be able to translate a word inside the room without leaving the app.
- Users should be able to save useful sentences.
- Users should be able to leave a room or match at any time.
- Free users should see clear limits before they reach them.
- Premium users should get the paid benefits promised by the app.

## 13. Success Metrics

The product is successful if users practice speaking often and feel more confident.

Important metrics:

- Number of new users.
- Number of users who complete profile setup.
- Number of users who join a room.
- Number of users who use Match One.
- Number of users who use Random Match.
- Number of conversations started.
- Number of conversations completed.
- Number of conversations that use Speech-to-Text.
- Number of AI suggestions used.
- Number of sentence notes saved.
- Number of users who return each week.
- Number of users who upgrade to premium.
- Number of premium users who keep using the app.

Learning success can be measured by:

- Users speaking more often.
- Users saving and reviewing useful sentences.
- Users saying they feel more confident.
- Users using better sentences over time.

## 14. Risks

The app has some risks.

## 14.1 Not Enough Users Online

If few users are online, matching may be slow.

Possible solution:

- Use random match.
- Show available rooms.
- Allow AI-only practice in the future.

## 14.2 Users May Feel Shy

Some users may be afraid to speak.

Possible solution:

- Provide incognito mode.
- Give AI sentence suggestions.
- Let users choose simple topics.

## 14.3 Bad User Behavior

Some users may say rude or unsafe things.

Possible solution:

- Add report user.
- Add block user.
- Add admin review.
- Add safety rules.

## 14.4 AI May Give Bad Suggestions

AI may sometimes give wrong or strange answers.

Possible solution:

- Use admin-approved learning content.
- Keep AI suggestions short.
- Let users ignore AI suggestions.
- Improve AI quality over time.

## 14.5 Matching May Not Be Perfect

The app may not always find the same topic, interest, and level.

Possible solution:

- Match by same mode first.
- Then try topic.
- Then try interest.
- Then try level.
- Tell the user when the match is close but not perfect.

## 14.6 Users May Not Understand Subscription Limits

Users may feel confused if they do not know why a feature is limited.

Possible solution:

- Explain free limits clearly.
- Show the user's current plan.
- Show premium benefits in simple words.
- Do not hide important speaking features without explanation.

## 14.7 Speech-to-Text May Be Wrong

Speech-to-Text may not always hear the user correctly.

This can happen because of:

- Background noise.
- Weak microphone quality.
- Strong accent.
- Fast speaking.
- Poor internet connection.

Possible solution:

- Tell users that the transcript may have mistakes.
- Let users continue speaking even if the transcript is not perfect.
- Let users save or edit important sentence notes.
- Use AI to improve the sentence after the speech is changed into text.

## 15. Assumptions

This PRD assumes:

- Users want to practice English speaking with other people.
- Users need support when they do not know what to say.
- Incognito mode will help shy users start speaking.
- Admin-created topics will make conversations easier.
- AI can help users improve sentences during practice.
- Speech-to-Text will help users review what they said.
- Matching by mode, topic, interest, and level will improve the user experience.
- Some users will pay for more AI help, more notes, and more practice.

## 16. Future Scope

Future versions may include:

- AI-only speaking partner.
- Voice call.
- Video call.
- Pronunciation feedback.
- Better transcript editing.
- Daily speaking challenge.
- Learning plan.
- Teacher or coach account.
- Advanced subscription plans.
- Mobile app.
- Group events.
- Conversation score.
- Advanced progress report.

## 17. Open Questions

These questions need answers later:

- Will the first version support text chat, voice chat, or both?
- How many people can join one room?
- Can users create their own rooms, or only admins?
- Can users create their own topics, or only admins?
- Should users see each other's country or location?
- Should incognito users have temporary names only?
- Should AI suggestions be private to the user or visible to the room?
- Should Speech-to-Text be turned on by default?
- Should full conversation transcripts be saved automatically?
- Should users be able to delete conversation transcripts?
- How long should conversation transcripts be saved?
- How long should sentence notes be saved?
- Should users be able to export sentence notes?
- What rules should be used when no good match is found?
- What should be included in the free plan?
- What should be included in the premium plan?
- Should payment be monthly, yearly, or both?
- Which payment methods should the app support?

