# MASTER SPEC — placedon.com (Kimi, v1.0, 2026-08-08)

> **This is the source document, preserved verbatim. Do not build directly from it.**
>
> Ten defects were found on ingest, three of them serious enough to break the build or
> re-introduce a bug we had already fixed. **Read `.claude/memory/SPEC_ERRATA.md` first** —
> it lists each one with the evidence, and the memory files (`PRODUCT.md`, `ARCHITECTURE.md`,
> `API_BUDGET.md`) already carry the corrected values.
>
> Where this document and the errata disagree, the errata wins.

---
<!-- p1 -->
PLACEDON.COM — CLAUDE CODE MASTER TECHNICAL
SPECIFICATION
Version 1.0 | For Claude Code Autonomous Development
Budget: Rs 5,000/month | Founder: Solo JAIN CMS Student
1. THE CLAUDE CODE OPERATING SYSTEM
1.1 The Loop Architecture
Claude Code must operate in a continuous R-D-B-V loop:
RESEARCH -> DECISION -> BUILD -> VERIFY -> (repeat)
RESEARCH Phase (15% of time)
• Read existing code before modifying
• Read .claude/memory/*.md for context
• Search for patterns in the codebase
• Check for existing similar implementations
DECISION Phase (10% of time)
• Choose the simplest implementation that works
• Prefer deterministic code over LLM calls
• Prefer SQL over vector search for structured data
• Prefer free/local tools over paid APIs
• Document the decision in a comment
BUILD Phase (60% of time)
• Write code following the conventions in Section 2
• One feature per session
• Write tests alongside code
• Never commit API keys
VERIFY Phase (15% of time)
• Run existing tests
• Test the new feature manually
• Check for TypeScript errors
• Check for Python lint errors
• Update .claude/today/TODAY.md


<!-- p2 -->
1.2 Memory Files (Claude Code Must Read These First)
Before EVERY session, Claude Code MUST read:
1. .claude/today/TODAY.md — What to build today
2. .claude/memory/PRODUCT.md — Product definition
3. .claude/memory/ARCHITECTURE.md — System architecture
4. .claude/memory/DATA.md — Data model
5. .claude/memory/API_BUDGET.md — Token/cost constraints
After EVERY session, Claude Code MUST update:
• .claude/today/TODAY.md with what was built
• .claude/memory/BLOCKERS.md if anything is blocked
1.3 The Research Command
When the user says /research [topic], Claude Code must:
1. Search the codebase for existing code related to [topic]
2. Read all files in .claude/memory/
3. Search online (if needed) for:
• Oﬀicial documentation
• Best practices
• Common pitfalls
4. Summarize findings in .claude/memory/RESEARCH_[topic].md
5. Recommend 3 implementation approaches with pros/cons
1.4 The Decision Command
When the user says /decision [options], Claude Code must:
1. Read the relevant research file
2. Evaluate each option against:
• Build time (must fit in 4 hours)
• Cost (must fit in daily API budget)
• Maintainability (can a student fix it?)
• Correctness (does it solve the user problem?)
3. Recommend ONE option with justification
4. Write the decision to .claude/memory/DECISIONS.md
2. CODING CONVENTIONS
2.1 Frontend (Next.js 14 + TypeScript)
File Structure Convention:
/frontend/app/
[route]/
page.tsx # Server component by default
layout.tsx # Only if needed
api/


<!-- p3 -->
[route]/
route.ts # API routes
/frontend/components/
ui/ # shadcn components ONLY
[feature]-form.tsx # Form components
[feature]-card.tsx # Display components
[feature]-item.tsx # List item components
/frontend/lib/
api.ts # All fetch calls
utils.ts # cn() and helpers
types.ts # Shared TypeScript types
Code Rules:
• Strict TypeScript. No any. Ever.
• Use async/await. No .then() chains.
• Use server components by default. Client components only for:
• Forms with state
• Animations
• Browser APIs (localStorage, clipboard)
• All API calls go through /frontend/lib/api.ts
• All colors use Tailwind classes. No hex codes inline.
• All icons from lucide-react
• All dates use date-fns (lightweight)
Component Template:
import { cn } from "@/lib/utils"
import { Card, CardHeader, CardTitle } from "@/components/ui/card"
interface FeatureCardProps {
title: string
description: string
severity: "critical" | "warning" | "good"
className?: string
}
export function FeatureCard({ title, description, severity, className }: FeatureCardProps) {
return (
<Card className={cn("border-l-4", {
"border-l-red-500": severity === "critical",
"border-l-yellow-500": severity === "warning",
"border-l-green-500": severity === "good",
}, className)}>
<CardHeader>


<!-- p4 -->
<CardTitle>{title}</CardTitle>
</CardHeader>
</Card>
)
}
2.2 Backend (FastAPI + Python)
File Structure Convention:
/backend/
main.py # App factory, CORS, middleware
config.py # Pydantic Settings, env vars
models/
schemas.py # All Pydantic models
database.py # Supabase client
routers/
__init__.py
diagnose.py # One router per feature
ask.py
generate.py
webhook.py
engine/
__init__.py
applicability.py # Rule engine (NO LLM)
retrieval.py # RAG pipeline
verifier.py # Abstention gate
generator.py # Document templates
services/
llm.py # Claude API wrapper (single file)
email.py # Resend wrapper
whatsapp.py # Twilio wrapper
data/
provisions.json # Legal corpus
templates/ # HTML templates
scripts/
ingest_pdf.py
seed_db.py
harvest_questions.py
tests/
test_applicability.py
test_retrieval.py
Code Rules:
• Pydantic v2 for ALL data validation
• Type hints everywhere. No untyped functions.
• One router per feature. No mega-files.
• Engine layer has NO external API calls. Pure Python.
• Services layer handles ALL external APIs.


<!-- p5 -->
• All LLM calls go through /backend/services/llm.py
• All database calls go through /backend/models/database.py
• Use pytest for tests. Minimum 80% coverage on engine layer.
• Use httpx for HTTP calls (async)
• Use loguru for logging (structured)
Function Template:
from typing import List, Optional
from pydantic import BaseModel
from loguru import logger
class ApplicabilityResult(BaseModel):
applies: bool
reasons: List[dict]
confidence: str
def check_posh_applicability(company: CompanyProfile) -> ApplicabilityResult:
logger.info(f"Checking PoSH applicability for {company.name}")
reasons = []
applies = False
if company.employee_count >= 10:
applies = True
reasons.append({
"rule": "Section 4(1), PoSH Act, 2013",
"text": "Every employer employing 10 or more employees shall constitute an IC",
"gazette_url": "https://egazette.gov.in/..."
})
return ApplicabilityResult(applies=applies, reasons=reasons, confidence="verified")
2.3 The Shared Types Contract
/shared/types.ts is the SINGLE SOURCE OF TRUTH. Both frontend and backend must use these
exact types:
export interface CompanyProfile {
id?: string
name: string
state: "KA" | "MH" | "DL" | "TG" | "TN" | "OTHER"
industry: "IT_SAAS" | "MANUFACTURING" | "RETAIL" | "SERVICES" | "OTHER"
employee_count: number
contractor_count: number
has_policy: boolean | null
has_ic: boolean
ic_date: string | null
has_return_filed: boolean | null
}
export interface Obligation {
id: string


<!-- p6 -->
title: string
description: string
severity: "critical" | "warning" | "good"
citation: string
action_text: string
action_href?: string
deadline?: string
}
export interface DiagnoseRequest extends CompanyProfile {}
export interface DiagnoseResponse {
company_profile: CompanyProfile
obligations: Obligation[]
risk_score: number
next_steps: string[]
}
export interface QAResponse {
answer: string
citations: Citation[]
confidence: "high" | "medium" | "abstain"
abstained: boolean
abstention_reason?: string
}
export interface Citation {
act: string
section: string
text: string
gazette_url: string
verified_by: string
verified_at: string
}
3. THE RAG PIPELINE (3-STAGE)
3.1 Stage 1: Keyword Router (Free, <10ms)
Purpose: Fast path for common questions. No LLM needed.
KEYWORD_MAP = {
"ic": ["ic_constitution", "internal committee", "presiding officer"],
"committee": ["ic_constitution"],
"annual return": ["annual_return"],
"return": ["annual_return"],
"policy": ["posh_policy", "display"],
"complaint": ["complaint_mechanism", "conciliation"],
"training": ["training", "awareness"],
"10 employees": ["ic_constitution", "applicability"],


<!-- p7 -->
"karnataka": ["state_override_ka"],
}
def keyword_route(question: str) -> Optional[List[str]]:
question_lower = question.lower()
matched_topics = set()
for keyword, topics in KEYWORD_MAP.items():
if keyword in question_lower:
matched_topics.update(topics)
return list(matched_topics) if matched_topics else None
When to use: 70% of questions hit this path. Costs Rs 0.
3.2 Stage 2: Vector Search (Free Local, <100ms)
Purpose: Semantic matching for questions that don’t hit keywords.
from sentence_transformers import SentenceTransformer
import numpy as np
_model = SentenceTransformer('all-MiniLM-L6-v2')
def embed_text(text: str) -> np.ndarray:
return _model.encode(text)
def vector_search(query: str, provisions: List[Provision], top_k: int = 5) -> List[Provision]:
query_embedding = embed_text(query)
scores = []
for provision in provisions:
prov_embedding = embed_text(provision.text[:500])
similarity = np.dot(query_embedding, prov_embedding)
scores.append((similarity, provision))
scores.sort(reverse=True)
return [p for _, p in scores[:top_k]]
When to use: 25% of questions. Costs Rs 0 (runs on your laptop/Render).
3.3 Stage 3: LLM Explanation (Paid, ~Rs 3-5 per call)
Purpose: Generate human-readable answer from verified provisions.
import os
from anthropic import Anthropic
from loguru import logger
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
SYSTEM_PROMPT = """You are Placedon, an HR compliance assistant for Indian SMEs.
CRITICAL RULES:
1. Answer ONLY using the provided legal text. Do not use outside knowledge.
2. If the answer is not in the text, say "I don't have verified information on this."


<!-- p8 -->
3. Cite the exact section number for every claim.
4. Do not hallucinate deadlines, penalties, or requirements.
5. Use simple language. The reader is an HR manager, not a lawyer.
6. Format: Direct answer -> Citation -> Action item (if applicable)
You are NOT giving legal advice. You are providing cited information from verified sources.
"""
def explain_provisions(question: str, provisions: List[dict], company: dict) -> str:
context = "\n\n".join([
f"[{p['act']}, Section {p['section']}]: {p['text'][:1000]}"
for p in provisions
])
prompt = f"Company: {company['employee_count']} employees in {company['state']}\n\nLegal
↪ Text:\n{context}\n\nQuestion: {question}\n\nAnswer:"
logger.info(f"LLM call for question: {question[:50]}...")
try:
response = client.messages.create(
model="claude-3-5-sonnet-20241022",
max_tokens=1024,
system=SYSTEM_PROMPT,
messages=[{"role": "user", "content": prompt}]
)
return response.content[0].text
except Exception as e:
logger.error(f"LLM call failed: {e}")
return "I apologize, I'm unable to answer right now. Please try again later."
When to use: 100% of answered questions go through this. But only AFTER retrieval.
3.4 The Abstention Gate (Critical)
Before ANY answer is shown to the user:
def should_abstain(provisions: List[Provision], answer: str) -> tuple[bool, str]:
if not provisions:
return True, "I don't have verified information on this topic yet."
unverified = [p for p in provisions if not p.verified_by]
if unverified:
return True, "This information is pending verification. Please consult your legal advisor."
if any(word in answer.lower() for word in ["pf amount", "gratuity amount", "salary calculation"]):
return True, "I don't perform payroll calculations. Please consult your CA."
return False, ""
This is your liability shield. Never skip this gate.
4. TOKEN BURN RATE & API BUDGET
4.1 Daily Budget: Rs 150-250 (50 LLM calls max)


<!-- p9 -->
Component Cost Per Call Daily Limit Daily Cost
Claude 3.5 Sonnet Rs 3-5 40 calls Rs 120-200
(explanation)
Claude 3.5 Sonnet Rs 5-8 5 calls Rs 25-40
(document polish)
Claude 3.5 Sonnet Rs 2-3 5 calls Rs 10-15
(error/debug)
Total 50 calls Rs 155-255
4.2 Cost Control Strategies
Strategy 1: Tiered Routing
def route_by_complexity(question: str, provisions: List[dict]) -> str:
simple = len(provisions) <= 2 and len(question) < 100
if simple:
return template_answer(question, provisions)
return explain_provisions(question, provisions)
Strategy 2: Response Caching
from functools import lru_cache
@lru_cache(maxsize=1000)
def cached_answer(question_hash: str, company_state: str) -> str:
pass
Strategy 3: Batch Processing
• Free users: Answers delivered via email in 10 minutes (batch at off-peak)
• Paid users: Instant answers
Strategy 4: Character Limits
• Input: Max 500 characters per question
• Context: Max 3 provisions per answer (top_k=3)
• Output: Max 800 tokens
4.3 Monthly API Budget Tracker
MONTHLY_BUDGET_RUPEES = 3500
class BudgetTracker:
def __init__(self):
self.calls_today = 0
self.cost_today = 0
self.calls_this_month = 0
self.cost_this_month = 0
def can_make_call(self, estimated_cost: float = 5.0) -> bool:
if self.cost_this_month + estimated_cost > MONTHLY_BUDGET_RUPEES:


<!-- p10 -->
return False
if self.calls_today >= 50:
return False
return True
def record_call(self, actual_cost: float):
self.calls_today += 1
self.cost_today += actual_cost
self.calls_this_month += 1
self.cost_this_month += actual_cost
5. DATA ARCHITECTURE
5.1 PostgreSQL Schema (Supabase)
CREATE TABLE provisions (
id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
act TEXT NOT NULL,
section TEXT NOT NULL,
text TEXT NOT NULL,
topic TEXT NOT NULL,
force_status TEXT NOT NULL CHECK (force_status IN ('in_force', 'draft', 'repealed')),
verified_by TEXT,
verified_at TIMESTAMP,
gazette_url TEXT NOT NULL,
parent_section TEXT,
state_override TEXT,
created_at TIMESTAMP DEFAULT NOW(),
UNIQUE(act, section, state_override)
);
CREATE TABLE company_profiles (
id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
name TEXT,
state TEXT NOT NULL,
industry TEXT NOT NULL,
employee_count INTEGER NOT NULL CHECK (employee_count >= 0),
contractor_count INTEGER DEFAULT 0,
has_policy BOOLEAN,
has_ic BOOLEAN DEFAULT FALSE,
ic_date DATE,
has_return_filed BOOLEAN,
last_training_date DATE,
created_by UUID,
created_at TIMESTAMP DEFAULT NOW(),
updated_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE qa_logs (
id UUID PRIMARY KEY DEFAULT gen_random_uuid(),


<!-- p11 -->
question TEXT NOT NULL,
company_id UUID REFERENCES company_profiles(id),
provisions_used UUID[],
applicability_trace JSONB,
llm_response TEXT,
citations JSONB,
abstained BOOLEAN DEFAULT FALSE,
abstention_reason TEXT,
confidence TEXT CHECK (confidence IN ('high', 'medium', 'abstain')),
created_at TIMESTAMP DEFAULT NOW(),
ip_address TEXT
);
CREATE TABLE obligations (
id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
company_id UUID REFERENCES company_profiles(id),
law TEXT NOT NULL,
title TEXT NOT NULL,
description TEXT,
severity TEXT CHECK (severity IN ('critical', 'warning', 'good')),
citation TEXT,
action_text TEXT,
deadline DATE,
completed BOOLEAN DEFAULT FALSE,
created_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE document_templates (
id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
name TEXT NOT NULL,
type TEXT NOT NULL,
template_html TEXT NOT NULL,
variables JSONB,
applicable_to JSONB,
created_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE generated_documents (
id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
company_id UUID REFERENCES company_profiles(id),
template_id UUID REFERENCES document_templates(id),
filled_data JSONB,
pdf_url TEXT,
created_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE feedback (
id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
qa_log_id UUID REFERENCES qa_logs(id),
rating INTEGER CHECK (rating BETWEEN 1 AND 5),
comment TEXT,


<!-- p12 -->
created_at TIMESTAMP DEFAULT NOW()
);
5.2 Data Flow Diagram
User submits form
|
v
[frontend] POST /api/diagnose
|
v
[backend] routers/diagnose.py
|
v
[backend] engine/applicability.py (pure Python, NO LLM)
|
v
[backend] models/database.py -> INSERT company_profile
|
v
[backend] engine/verifier.py -> Check if rules are verified
|
v
[backend] services/llm.py -> ONLY if explanation needed
|
v
[backend] models/database.py -> INSERT qa_log (audit trail)
|
v
[frontend] Display result + citations
6. API STRATEGY
6.1 Paid APIs (Use Sparingly)
API Purpose Cost Limit
Anthropic Claude Answer explanations Rs 3-5/call 50/day
Resend Monday Brief emails Rs 0 (3K free/mo) 100/day
Twilio WhatsApp Bot responses Rs 0 (trial) 1K conv/mo
6.2 Free APIs (Use Liberally)
API Purpose Limit
Supabase Database + Auth 500MB, 2GB transfer
Vercel Frontend hosting 100GB bandwidth
Render Backend hosting 512MB RAM


<!-- p13 -->
Table 3 – continued
API Purpose Limit
GitHub Code + Actions Unlimited public
6.3 Local/Free Tools (No API Needed)
Tool Purpose
sentence-transformers Embeddings (local CPU)
pdfplumber PDF text extraction
weasyprint PDF generation
jinja2 Template engine
pytest Testing
loguru Logging
6.4 API Fallback Chain
# If primary API fails, fall back:
# Claude API down -> Use OpenRouter free tier
# OpenRouter down -> Return cached answer
# No cache -> Abstain: "Service temporarily unavailable"
# Supabase down -> Use local SQLite (read-only fallback)
# Render down -> Show static "We'll be back" page
7. FEATURE MODULES
7.1 Module: Free Checker (Week 1)
Complexity: Low | Build Time: 1 day | LLM Cost: Rs 0
Architecture:
• Frontend: Form -> API call -> Result page
• Backend: Pydantic validation -> applicability.py -> JSON response
• No LLM. No database write (anonymous).
Files:
/frontend/app/diagnose/page.tsx
/frontend/app/result/page.tsx
/frontend/components/checker-form.tsx
/frontend/components/result-card.tsx
/frontend/components/obligation-item.tsx
/frontend/components/citation-badge.tsx
/backend/routers/diagnose.py
/backend/engine/applicability.py
/backend/models/schemas.py


<!-- p14 -->
7.2 Module: Cited Q&A (Week 2)
Complexity: Medium | Build Time: 2 days | LLM Cost: Rs 150-200/day
Architecture:
• Frontend: Chat interface
• Backend: keyword_route -> vector_search -> verifier -> llm.explain -> qa_log
Files:
/frontend/app/ask/page.tsx
/frontend/components/chat-interface.tsx
/frontend/components/message-bubble.tsx
/backend/routers/ask.py
/backend/engine/retrieval.py
/backend/engine/verifier.py
/backend/services/llm.py
7.3 Module: Document Generator (Week 3)
Complexity: Medium | Build Time: 2 days | LLM Cost: Rs 50-100/day
Architecture:
• Frontend: Form -> Preview -> Download
• Backend: Template retrieval -> Jinja2 fill -> weasyprint PDF -> Storage
Files:
/frontend/app/generate/[type]/page.tsx
/frontend/components/document-preview.tsx
/backend/routers/generate.py
/backend/engine/generator.py
/backend/data/templates/ic_order.html
/backend/data/templates/offer_letter.html
7.4 Module: WhatsApp Bot (Week 4)
Complexity: Medium | Build Time: 2 days | LLM Cost: Rs 100-150/day
Architecture:
• Twilio webhook -> FastAPI endpoint -> Same ask.py logic -> Twilio reply
Files:
/backend/routers/webhook.py
/backend/services/whatsapp.py
/backend/engine/whatsapp_formatter.py
7.5 Module: Resume Screener (Week 6)
Complexity: High | Build Time: 3 days | LLM Cost: Rs 200-300/day (batch)
Architecture:


<!-- p15 -->
• Frontend: Upload JD + Resumes -> Table
• Backend: pdfplumber extract -> Claude structured extraction -> Matching algorithm -> Ranked
list
Files:
/frontend/app/tools/resume-screener/page.tsx
/frontend/components/resume-upload.tsx
/frontend/components/candidate-rank.tsx
/backend/routers/resume.py
/backend/engine/resume_parser.py
/backend/engine/resume_matcher.py
8. SECURITY & PII RULES
8.1 The 6 Hard Rules
1. NO employee-level PII ever. Only company aggregate data.
2. NO salary data storage. Analyze and delete.
3. NO training on customer data. Zero. State it publicly.
4. Encrypt all DB connections. SSL only.
5. API keys in .env only. Never commit. Use .env.example for docs.
6. Rate limit everything. 5 requests/minute per IP for free tier.
8.2 Environment Variables
# /backend/.env (NEVER COMMIT)
ANTHROPIC_API_KEY=sk-ant-...
SUPABASE_URL=https://....supabase.co
SUPABASE_KEY=eyJ...
RESEND_API_KEY=re_...
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
DATABASE_URL=postgresql://...
8.3 Rate Limiting
from slowapi import Limiter
from slowapi.util import get_remote_address
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
@app.post("/api/diagnose")
@limiter.limit("5/minute")
async def diagnose(request: Request, data: DiagnoseRequest):
...


<!-- p16 -->
9. MONITORING & DEBUGGING
9.1 Free Monitoring Stack
Tool Purpose Cost
Vercel Analytics Frontend metrics Rs 0
Render Dashboard Backend uptime Rs 0
Supabase Dashboard DB performance Rs 0
Google Search Console SEO Rs 0
Custom /admin Business metrics Rs 0
9.2 Admin Dashboard (Simple)
/frontend/app/admin/page.tsx (password protected)
Metrics:
- Total users today/this week/this month
- Total checks completed
- Most asked questions (top 10)
- Abstention rate
- API cost today/this month
- Error rate
- Conversion rate (free -> paid)
9.3 Logging Convention
logger.info("diagnose.start", company_state="KA", employees=14)
logger.info("diagnose.applicable", law="posh", applies=True)
logger.info("llm.call", question_length=120, provisions_count=3)
logger.info("llm.response", tokens_used=450, cost_inr=4.2)
logger.warning("abstain.gate_triggered", reason="unverified_provisions")
logger.error("api.failure", endpoint="/api/diagnose", error=str(e))
10. THE CLAUDE CODE PROMPT LIBRARY
Prompt 1: Session Start (Every Morning)
Read these files in order:
1. .claude/today/TODAY.md
2. .claude/memory/PRODUCT.md
3. .claude/memory/ARCHITECTURE.md
4. .claude/memory/API_BUDGET.md
Today's goal: [STATE GOAL]
Constraints:
- One feature only. No scope creep.
- Follow coding conventions in Section 2.


<!-- p17 -->
- No API keys in code. Use env vars.
- Write tests for engine layer.
- Update TODAY.md when done.
Start by reading existing code in the relevant directories.
Prompt 2: Build Feature
Build [FEATURE NAME] following the spec in Section 7.[X].
Files to create/modify:
- [list files]
Requirements:
- [specific requirements]
- Mobile responsive
- TypeScript strict / Pydantic v2
- Error handling for all external calls
- Rate limiting on API routes
Do NOT:
- Use any new paid APIs
- Add dependencies not in requirements.txt
- Break existing tests
Prompt 3: Fix Bug
There's a bug: [DESCRIBE]
Reproduction steps:
1. [step 1]
2. [step 2]
Expected: [expected behavior]
Actual: [actual behavior]
Read the relevant files. Identify root cause. Fix it.
Add a regression test.
Prompt 4: Research Topic
Research [TOPIC] for placedon.com.
Search the codebase for existing implementations.
Search online for:
- Official documentation
- Best practices
- Common pitfalls
Summarize in .claude/memory/RESEARCH_[topic].md with:


<!-- p18 -->
- 3 implementation approaches
- Pros/cons of each
- Recommended approach for our constraints
Prompt 5: Optimize Cost
Review [FILE/SERVICE] for cost optimization.
Check:
- Can we reduce LLM calls?
- Can we cache more aggressively?
- Can we use a cheaper model for simple tasks?
- Can we batch requests?
Implement the top 2 optimizations.
11. DEPLOYMENT CHECKLIST
Before every deploy:
• All tests pass (pytest in /backend)
• TypeScript compiles (npm run build in /frontend)
• No API keys in code
• .env is in .gitignore
• Rate limiting is active
• Admin dashboard shows no errors
• Mobile test passed
• TODAY.md updated
• Git commit with descriptive message
12. EMERGENCY PROTOCOLS
API Budget Exhausted
LLM_MODE = os.getenv("LLM_MODE", "normal") # "normal" | "budget" | "offline"
if LLM_MODE == "budget":
# Use keyword-only answers, no Claude
# Batch all requests, process at 3 AM
pass
Database Down
import json
with open("/backend/data/provisions_fallback.json") as f:
provisions = json.load(f)


<!-- p19 -->
LLM Hallucination Detected
SUSPICIOUS_PATTERNS = ["I believe", "I think", "probably", "might be"]
if any(p in answer.lower() for p in SUSPICIOUS_PATTERNS):
return abstain("Unable to verify this answer. Please consult your legal advisor.")
13. START COMMAND
Every day, run this in your terminal:
cd placedon
claude
Then paste:
Read .claude/today/TODAY.md and .claude/memory/*.md.
Today's goal is stated in TODAY.md.
Follow the coding conventions in the master spec.
Build the feature. Test it. Update TODAY.md.
APPENDIX A: MEMORY FILE TEMPLATES
.claude/memory/PRODUCT.md
# Product Definition
Name: Placedon.com
Tagline: "Every HR team deserves an expert in the room."
V1 Scope: PoSH compliance for Karnataka companies
V2 Scope: EPF, ESI, Karnataka S&E
V3 Scope: JD generator, offer letters, policies
V4 Scope: Resume screener, analytics, predictions
Golden Rule: LLM explains. Code decides. Lawyer verifies.
.claude/memory/ARCHITECTURE.md
# System Architecture
Frontend: Next.js 14 (App Router) + Tailwind + shadcn/ui
Backend: FastAPI + Python 3.11
Database: Supabase PostgreSQL
LLM: Anthropic Claude 3.5 Sonnet (via services/llm.py ONLY)
Embeddings: sentence-transformers all-MiniLM-L6-v2 (local)
PDF: pdfplumber (extract) + weasyprint (generate)
Email: Resend
WhatsApp: Twilio
Hosting: Vercel (frontend) + Render (backend)
.claude/memory/API_BUDGET.md
# API Budget


<!-- p20 -->
Monthly: Rs 3,500
Daily: Rs 150-250
Per call: Rs 3-5 (Claude)
Max calls/day: 50
Current spend today: Rs 0
Current spend this month: Rs 0
Remaining: Rs 3,500
APPENDIX B: QUICK REFERENCE
Task Command
Start dev cd frontend && npm run dev + cd backend && uvicorn
main:app --reload
Run tests cd backend && pytest
Deploy git push (Vercel auto-deploys)
Check logs cd backend && tail -f app.log
DB console supabase.com -> Table Editor
API test curl -X POST http://localhost:8000/api/diagnose -H
"Content-Type: application/json" -d
'{"employees":14,...}'
This specification is living documentation. Update it as the product evolves. Last updated: 2026-08-08
