# Privacy and security notes

A short record of how the assistant handles personal data, in the spirit of a data protection impact assessment. It describes the design of this demo; a real deployment needs the company's data protection officer and works council involved before launch.

## Data processed

| Data | Purpose | Stored | Retention |
|---|---|---|---|
| Question text | Answer the question; find gaps in the policies | Yes, after redaction | 90 days |
| Role (employee, manager, HR) | Access control | Yes | 90 days |
| Session token | Rate limiting, grouping feedback | Yes, a random value from the browser with no link to the person | 90 days |
| Feedback (helpful or not, optional comment) | Measure answer quality | Yes, comment redacted | 90 days |
| Name, employee ID, email, phone, IBAN, tax ID, dates in the question | Not needed | No, replaced with tags before processing | n/a |
| User account, IP address | Not needed | No | n/a |

## Principles applied

- Data minimisation: the assistant does not need to know who is asking, only their role. No user ID is stored.
- Purpose limitation: the log is used to measure quality and find missing policy content, not to monitor employees. The HR-only statistics endpoint shows counts and shares, never individual questions.
- Storage limitation: rows are deleted after 90 days on every start of the service.
- Access control: restricted policies are removed before retrieval, and a test checks that no restricted passage is ever cited for a lower role.
- External processing: without an LLM configured, nothing leaves the service. With one, only the redacted question and the retrieved passages are sent; a provider in the EU, or a self-hosted model, should be chosen, with a data processing agreement.
- Co-determination: in Germany, a system that could be used to monitor employees needs the works council's agreement. The design avoids monitoring by not storing identities, but the agreement is still needed.

## Security measures

- The container runs as a non-root user; Kubernetes enforces it with `runAsNonRoot`.
- The role is taken from the identity proxy header in production; the request body cannot raise it.
- Request bodies are limited to 4,000 bytes and questions to 500 characters; each session may ask 30 questions per minute.
- Database credentials and LLM keys come from a Kubernetes Secret, never from the image or the repository.
- Prompt injection: the model only sees the retrieved passages and must cite them. Replies without valid citations are discarded, so an instruction hidden in a question cannot make the assistant reveal content the role may not see, because that content was never retrieved.

## Known limits

- Redaction is pattern-based. It catches common formats, not every way someone can describe themselves. Free-text comments are redacted the same way.
- The policies are fictional and simplified, and the answers are not legal advice.
