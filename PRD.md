# PRD: TrackAJob

## 1. Summary

TrackAJob is a web app that helps job seekers do two things well: keep track of every job application they send, and tailor their resume to each job post before they apply.

The problem it solves: applying to many jobs with the same generic resume gets poor results. Tailoring a resume by hand for every posting takes too long, and most people lose track of what they sent, when, and to whom. TrackAJob puts both jobs in one place. You save a job post, you tailor your resume against it, and both live on the same card.

## 2. Problem statement

- Job seekers send out many applications and lose track of them in spreadsheets, bookmarks, or email threads.
- Editing a resume for each job post is slow and repetitive. Most people skip it, and their applications get filtered out by applicant tracking systems (ATS) or ignored by recruiters.
- Free-form resume tools exist, but they do not connect the resume to a specific job post, and they do not check whether the result passes an ATS scan.
- Job seekers also cannot tell which version of their resume they sent to which employer.

## 3. Goals

1. Let a user create an account and maintain a personal profile.
2. Give the user a resume builder that produces clean, standard, ATS-parseable documents.
3. Let the user attach a saved job post to a resume tailor pass, so each application gets a version of the resume that matches that post.
4. Accept a plain prompt from the user (for example "make this more senior" or "use simpler wording") and apply it to the resume content without breaking the layout.
5. Export the result as PDF, Word (.docx), or image (PNG).
6. Keep a record of every application: company, role, source, date, status, and which resume version was sent.

Non-goals for the first release:

- Automatic applying on behalf of the user ("one click apply").
- Cover letter generation (planned for a later release).
- Email or calendar integrations.
- Recruiter-facing features. This product is for job seekers only.

## 4. Users

Primary user: an active job seeker who applies to several roles per week and wants to improve their response rate.

Secondary personas:

- New graduate, first resume, little sense of what a good resume looks like.
- Career switcher, needs to reframe existing experience for a new field.
- Experienced professional who applies selectively and wants a quick tailoring pass per role.

## 5. User stories

### Accounts

- As a user, I can sign up with email and password.
- As a user, I can log in and log out.
- As a user, I can recover my password through email.

### Profile

- As a user, I can edit my name, contact details, location, and links (portfolio, GitHub, LinkedIn).
- As a user, my profile pre-fills my resume header so I do not type it twice.

### Resume builder

- As a user, I can create and edit one or more resumes with sections: header, summary, work experience, education, skills, projects, certifications.
- As a user, I can reorder sections and entries.
- As a user, I can pick from a small set of ATS-safe templates: single column, standard fonts, no tables or graphics in the parsed text.
- As a user, I can save a resume as the base version and derive tailored versions from it.

### Job posts

- As a user, I can save a job post by pasting the text or description, along with company, role title, source, and link.
- As a user, I can import job details through integrations for job boards such as LinkedIn, Indeed, and JobStreet, when those integrations are available.
- As a user, I can see all my saved jobs in one list with their status: interested, applied, interview, offer, rejected, closed.

### Resume tailoring

- As a user, I can open a job post and ask for a tailored version of my resume against it.
- As a user, I can give a plain instruction in my own words, and the app applies it to the resume content. Examples: "shorten this to one page", "emphasize my project management work", "rewrite the summary for this role".
- As a user, I can see what changed between my base resume and the tailored one, and revert any change.
- As a user, the tailored resume keeps a fixed ATS-safe layout no matter what the prompt asks for.

### Export

- As a user, I can export a resume as PDF.
- As a user, I can export a resume as a Word file (.docx).
- As a user, I can export a resume as an image (PNG), for quick sharing.

### Application tracker

- As a user, I can mark a job as applied and record which resume version I sent.
- As a user, I can update the status of each application and add notes.
- As a user, I can see counts by status on a simple dashboard.

## 6. Functional requirements

### FR-1 Authentication

- Email and password sign up with email verification.
- Session based login with a standard reset password flow.
- Passwords stored hashed (bcrypt or argon2).

### FR-2 Profile

- CRUD on profile fields listed above.
- Profile feeds the default header of new resumes.

### FR-3 Resume builder

- Multiple resumes per user.
- Sections: header, summary, experience, education, skills, projects, certifications.
- Drag to reorder sections and entries.
- Autosave.
- Templates: at least two ATS-safe templates at launch.

### FR-4 Tailoring

- A user prompt, free text, up to a reasonable length limit, applied to a chosen resume and job post.
- The system returns the tailored resume content and a diff against the base.
- The system refuses structural instructions that would break ATS parsing (for example, putting text in images) and says so in plain language.
- Every tailored version is stored and linked to its job post.

### FR-5 Job post ingestion

- Manual paste of a job description, always available.
- Import hooks for external job boards. The first integration target is one board where terms allow it, with a connection layer designed to add more boards without redesign.
- Store: title, company, source, link, description text, date saved, status.

### FR-6 Export

- PDF export that preserves the on-screen layout.
- DOCX export with proper heading and list styles so parsing works in Word and Google Docs.
- PNG export rendered from the same layout.
- File naming convention: `Name_Role_Company` by default.

### FR-7 Tracker

- Statuses: interested, applied, interview, offer, rejected, closed.
- Notes per application.
- Timestamps on status changes.

## 7. Non-functional requirements

- Latency: resume editor interactions under 100 ms locally; tailoring requests should show progress and return within a reasonable wait, with streaming where possible.
- Data safety: resumes and applications are private to the user account. No public pages. Deletion of an account removes all data.
- Reliability: exports must be byte-stable and readable in common tools (Adobe Reader, Word, Google Docs, ATS parsers).
- Accessibility: usable with keyboard only and a screen reader on core flows.
- Cost control: AI tailoring calls are metered per user with a fair use cap that can be adjusted.

## 8. Success metrics

- Activation: percentage of new users who save at least one job post and export at least one tailored resume in the first week.
- Engagement: average tailored resumes per user per week.
- Outcome signal: self-reported status progression, share of applications moving from applied to interview.
- Retention: weekly returning users who used the tracker or the tailor in the last 7 days.

## 9. Open questions

- Which job board integration to build first, based on what their terms permit.
- Fair use cap and any paid tier around the AI tailoring feature.
- Whether to support multiple languages for resumes before v1 or after.
