# TrackAJob, explained like you are five

No jargon. If you have never built an app, start here.

---

## What is this thing?

Imagine you are applying for jobs. You send your resume to twenty companies.
Then someone calls and says "we loved the version you sent us" and you think…
*which version?*

TrackAJob is a notebook for your job hunt. It remembers:

- **every job you applied to**, and what happened to each one;
- **every version of your resume**, and which one you sent where.

It also has a helper that rewrites your resume for a specific job — like a
friend who reads the job ad and says "lead with the part where you fixed the
slow website."

---

## The two halves

Think of a restaurant.

**The front of house** is what you see: the menu, the tables, the waiter.
That is the part built with **React**. It runs in your web browser.

**The kitchen** is where the food is actually made. You never see it. That is
the **Python** server. It stores your data and does the hard work.

The waiter is how they talk. When you click "Save", the waiter carries your
order to the kitchen, and carries the food back. Those trips are called the
**API**.

You cannot cook in the dining room, and you cannot seat guests in the kitchen.
Keeping them separate is why the app can grow without everything breaking.

---

## Where your stuff is kept

A **database** is a very tidy filing cabinet.

Ours has drawers:

- one drawer for people who signed up;
- one for resumes;
- one for **every version** of every resume;
- one for job applications.

Each piece of paper in a drawer is a **row**. When you save a note, we write a
new line in the right drawer.

**Important:** your drawer is yours. When you log in, the app checks who you
are, then only ever opens *your* drawers. That is called **isolation**, and it
is the single most important safety rule. If that broke, you would see other
people's resumes. We test for it every time.

---

## What happens when you click "Save"

1. You type something. The screen remembers it in the moment.
2. You stop typing for about a second.
3. The app quietly sends it to the kitchen.
4. The kitchen writes it in the filing cabinet.
5. The little dot next to the title turns green and says "Saved".

If you close the tab in a hurry, the app still tries to save on the way out.
If you try to leave with unsaved changes, it asks first. Losing your work
would be unforgivable, so we guard it three ways.

---

## The resume helper, and why it refuses to lie

The helper uses an **AI model** — a computer program that is good at writing.
You give it your resume and a job ad. It rewrites your resume to fit.

The danger is obvious: an AI will happily invent that you "led a team of 40"
because it sounds good. That would get you caught in an interview.

So the app has a rule: **the AI may rearrange your words, never invent new
facts.** After the AI answers, the app checks every line. If a line contains
nothing that appears in your original resume, it gets thrown out and you are
told why.

An impressive lie is worse than a plain truth.

---

## Why the resume file matters so much

Most big companies do not have a person read your resume first. A robot does.

That robot is called an **ATS** (Applicant Tracking System). It opens your
file, pulls out the text, and files you under keywords.

Robots are fussy. They choke on:

- two-column layouts;
- tables;
- text hidden inside pictures;
- fancy fonts.

So our resume is deliberately boring: one column, normal fonts, plain
headings. Boring is what gets read.

**A real bug we found:** the app used to make PDFs in a way that turned the
symbol `€` and letters like `é` into a question mark `?`. A person named
"José" became "Jos?". The file looked fine on screen, but the robot read
garbage. We fixed it by embedding a proper font, and now a test checks that
accents and currency symbols survive.

That is why we test files by *reading them back*, not just by looking at them.

---

## Importing a job from a link

You paste a job link. The app fetches the page and tries to read the job title,
company, and description.

It reads in order of reliability:

1. **Structured data** — many sites include a hidden block of facts for search
   engines. If it is there, this is the best source.
2. **Preview tags** — the title and blurb that show up when you share a link.
3. **Known patterns** — specific rules for LinkedIn, Kalibrr, and others.
4. **Guesswork** — the biggest block of text on the page.

**It does not always work, and it says so.** Some sites (JobStreet, Indeed)
put up a robot wall that blocks automated visits. When that happens the app
tells you plainly and asks you to paste the description instead. It never
pretends it succeeded.

There is also a safety rule: the app refuses to fetch private addresses, so
nobody can trick it into reading files from inside our own server. That trick
is called **SSRF**, and it is a classic way to break into systems.

---

## The numbers page

The Statistics tab counts things:

- how many applications you sent;
- how many ever got a reply;
- where they came from.

One number needs explaining: the **funnel**. It shows how many applications
*ever reached* each stage, not just where they are now. If a job went
applied → interview → rejected, it still counts as having reached "applied".
Otherwise the chart would shrink every time you got bad news, which would be
both wrong and depressing.

You can download all of it as a spreadsheet file (**CSV**), or print it.

---

## Light and dark

The app is a notebook, so it starts as cream paper. There is a switch in the
corner for dark mode. It remembers your choice.

We do not automatically copy your computer's setting, because a brand new user
should get the paper look. If you want dark, you ask for dark.

---

## Words you will hear

| Word | What it actually means |
| --- | --- |
| **Frontend** | The part in your browser. What you see and click. |
| **Backend** | The part on a server. Stores data, does hard work. |
| **API** | The waiter carrying messages between the two. |
| **Database** | The filing cabinet. |
| **Endpoint** | One specific door into the backend, like `/api/jobs`. |
| **Route** | One specific screen, like `#/resumes/3`. |
| **ATS** | The robot that reads your resume before a human does. |
| **SSRF** | Tricking a server into fetching something it should not. |
| **ADR** | A short note explaining *why* we made a big decision. |
| **Test** | A tiny program that checks the app still works. |
| **Deploy** | Putting the app on the internet for real users. |

---

## If you want to change something

1. **Read `docs/guidelines.md`.** It explains the rules and the reasons.
2. **Run the tests first**, so you know what "working" looks like:
   `.venv/Scripts/python.exe -m pytest -q`
3. **Make one small change.**
4. **Run the tests again.** If something goes red, you broke it — that is the
   tests doing their job, not being annoying.
5. **Look at it in a browser.** Tests cannot see that a button is off-screen.

And the most useful habit: **if you fix a bug, prove the test can fail.**
Undo your fix, watch the test go red, put the fix back. A test that has never
failed is just decoration.
