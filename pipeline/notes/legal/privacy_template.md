# Privacy Policy Template

_Effective date: [DATE]. Data Controller: [ENTITY, CONTACTS]._

## 1. Information Processed
- **Account Data:** Email address, password hash (PBKDF2), registration timestamp, role.
- **Billing:** Credit balance, ledger of processing charges and top-ups.
- **User Content:** Scripts, images, audio reference recordings, output video files (stored in isolated tenant directories).
- **Technical Logs:** Access timestamps, IP addresses for security logging, and API request audits.

## 2. Purpose of Processing
Delivering automated video generation, securing user accounts, preventing service abuse, and providing technical support.

## 3. Third-Party Disclosures
Model requests under Bring Your Own Key (BYOK) configurations are routed directly to user-configured upstream providers (e.g. OpenAI, OpenRouter, ElevenLabs) using the user's API credentials. User data is never sold.

## 4. Security Measures
Passwords hashed with salted PBKDF2; session authentication via secure HttpOnly cookies; tenant workspace data isolation on disk.

## 5. Contact
Inquiries regarding data access, corrections, or deletion: [CONTACT EMAIL].
