# Data Security & Production Architecture

## Executive Summary

This document covers the **complete data security architecture** for a production voice AI system handling sensitive customer data (PII, payment info, health data). Covers:

- **Data storage** - Where everything lives (multi-tenant isolation)
- **Security boundaries** - Encryption, access control, network segmentation
- **Compliance** - GDPR, CCPA, HIPAA, PCI-DSS
- **Policies** - Where business rules live (database vs code vs external)
- **Secrets management** - API keys, credentials, certificates
- **Audit & monitoring** - Complete trail for security incidents

**Threat Model:** Restaurant reservation system handling:
- PII (names, phone numbers, emails)
- Payment data (credit cards for deposits)
- Health data (dietary restrictions, allergies)
- Business data (availability, menu, pricing)

---

## Table of Contents

1. [Data Storage Architecture](#data-storage-architecture)
2. [Multi-Tenant Isolation](#multi-tenant-isolation)
3. [Database Schema with Security](#database-schema-with-security)
4. [Encryption Strategy](#encryption-strategy)
5. [Access Control & Authentication](#access-control--authentication)
6. [Secrets Management](#secrets-management)
7. [Network Security](#network-security)
8. [Compliance Requirements](#compliance-requirements)
9. [Audit & Monitoring](#audit--monitoring)
10. [Data Retention & Deletion](#data-retention--deletion)
11. [Backup & Disaster Recovery](#backup--disaster-recovery)
12. [Policy Storage & Management](#policy-storage--management)
13. [Deployment Architecture](#deployment-architecture)

---

## 1. Data Storage Architecture

### High-Level Storage Topology

```
┌─────────────────────────────────────────────────────────────────┐
│                   PRODUCTION DATA STORAGE                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  PRIMARY DATABASE (PostgreSQL 15+ with RLS)             │   │
│  │  - Encrypted at rest (AES-256)                          │   │
│  │  - Row-level security for multi-tenant isolation        │   │
│  │  - Connection pooling (PgBouncer)                       │   │
│  │  - Read replicas for analytics                          │   │
│  │                                                           │   │
│  │  Tables:                                                  │   │
│  │    • tenants                  (restaurant accounts)      │   │
│  │    • voice_sessions           (call data, notepad)       │   │
│  │    • reservations             (confirmed bookings)       │   │
│  │    • customers                (PII - encrypted fields)   │   │
│  │    • availability             (restaurant schedules)     │   │
│  │    • menu_embeddings          (vector search, pgvector) │   │
│  │    • policy_embeddings        (business rules, RAG)     │   │
│  │    • audit_logs               (security events)         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  CACHE LAYER (Redis 7+ with TLS)                        │   │
│  │  - Session tokens (short-lived)                          │   │
│  │  - Rate limiting counters                                │   │
│  │  - RAG query cache (hot data)                           │   │
│  │  - Escalation queue (in-memory, persistent backup)      │   │
│  │  - TTL on all keys (auto-expiry)                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  OBJECT STORAGE (S3 / GCS with versioning)              │   │
│  │  - Call recordings (encrypted, tenant-isolated buckets) │   │
│  │  - Transcripts (long-term storage)                       │   │
│  │  - Backup dumps (encrypted, cross-region)               │   │
│  │  - ML model artifacts (versioned)                        │   │
│  │  - Lifecycle policies (auto-delete after retention)     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  SECRETS VAULT (HashiCorp Vault / AWS Secrets Manager)  │   │
│  │  - API keys (Deepgram, OpenAI, Twilio)                  │   │
│  │  - Database credentials (rotated every 90 days)         │   │
│  │  - Encryption keys (KMS-backed)                          │   │
│  │  - OAuth tokens                                          │   │
│  │  - TLS certificates                                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  LOGGING & MONITORING (Separate from app data)          │   │
│  │  - Application logs (structured JSON, no PII)           │   │
│  │  - Audit logs (immutable, WORM storage)                 │   │
│  │  - Metrics (Prometheus, aggregated)                      │   │
│  │  - Alerts (PagerDuty, Slack for security events)        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Data Classification

| Data Type | Classification | Storage Location | Encryption | Retention | Access Level |
|-----------|---------------|------------------|------------|-----------|--------------|
| Call audio | **Sensitive** | S3 (tenant buckets) | AES-256 + TLS | 90 days | Tenant admin only |
| Transcripts | **Sensitive** | PostgreSQL / S3 | Encrypted | 1 year | Tenant + agents |
| Notepad (PII) | **Highly Sensitive** | PostgreSQL | Field-level encryption | 7 years | Need-to-know |
| Payment info | **PCI Data** | External (Stripe) | N/A (tokenized) | N/A | Never stored |
| Health data (allergies) | **PHI** | PostgreSQL | HIPAA-compliant encryption | 7 years | Restricted |
| Availability | **Internal** | PostgreSQL | At-rest encryption | Indefinite | All users |
| Menu | **Public** | PostgreSQL | At-rest encryption | Indefinite | Public API |
| Audit logs | **Critical** | Immutable storage | Encrypted + signed | 7 years | Security team only |

---

## 2. Multi-Tenant Isolation

### Tenant Model

**Every restaurant is a separate tenant.** Data must be **100% isolated** - Restaurant A can NEVER see Restaurant B's data.

### Tenant Table (Master)

```sql
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT UNIQUE NOT NULL,  -- e.g., 'joes-pizza'
    name TEXT NOT NULL,

    -- Contact info
    contact_email TEXT NOT NULL,
    contact_phone TEXT,

    -- Subscription & limits
    plan TEXT NOT NULL DEFAULT 'free',  -- free|basic|pro|enterprise
    max_calls_per_month INT NOT NULL DEFAULT 100,
    max_agents INT NOT NULL DEFAULT 1,

    -- Security
    api_key_hash TEXT NOT NULL,  -- Hashed, never plaintext
    webhook_secret TEXT NOT NULL,
    allowed_ip_ranges INET[],  -- Optional IP whitelist

    -- Feature flags
    features JSONB DEFAULT '{}',  -- {"escalation": true, "rag": true}

    -- Compliance
    data_residency TEXT DEFAULT 'us-east-1',  -- Where data must stay
    retention_days INT DEFAULT 365,

    -- Status
    status TEXT NOT NULL DEFAULT 'active',  -- active|suspended|deleted
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMP  -- Soft delete
);

-- Indexes
CREATE UNIQUE INDEX idx_tenants_slug ON tenants(slug) WHERE deleted_at IS NULL;
CREATE INDEX idx_tenants_status ON tenants(status);
```

### Row-Level Security (RLS)

**Every table with tenant data MUST use PostgreSQL RLS:**

```sql
-- Enable RLS on voice_sessions
ALTER TABLE voice_sessions ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only see their tenant's data
CREATE POLICY tenant_isolation_policy ON voice_sessions
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Policy: Superusers can see all (for support, with audit)
CREATE POLICY superuser_policy ON voice_sessions
    FOR ALL
    TO superuser_role
    USING (true);
```

### Application-Level Tenant Context

**File:** `services/tenant_context.py`

```python
from contextvars import ContextVar
from typing import Optional
import uuid

# Thread-safe tenant context (per-request)
_tenant_id: ContextVar[Optional[uuid.UUID]] = ContextVar('tenant_id', default=None)

class TenantContext:
    """Manages tenant context for multi-tenant isolation."""

    @staticmethod
    def set_tenant(tenant_id: uuid.UUID) -> None:
        """Set current tenant (called at request start)."""
        _tenant_id.set(tenant_id)

    @staticmethod
    def get_tenant() -> uuid.UUID:
        """Get current tenant (raises if not set)."""
        tid = _tenant_id.get()
        if tid is None:
            raise RuntimeError("Tenant context not set - security violation!")
        return tid

    @staticmethod
    def clear() -> None:
        """Clear tenant context (called at request end)."""
        _tenant_id.set(None)

    @staticmethod
    async def set_postgres_context(conn) -> None:
        """Set PostgreSQL session variable for RLS."""
        tenant_id = TenantContext.get_tenant()
        await conn.execute(
            "SET LOCAL app.current_tenant_id = $1",
            str(tenant_id)
        )
```

### Usage in VoiceSession

```python
class VoiceSession:
    def __init__(self, websocket: WebSocket, tenant_id: uuid.UUID):
        # Set tenant context FIRST (security-critical)
        TenantContext.set_tenant(tenant_id)

        self.tenant_id = tenant_id
        # ... rest of init ...

    async def _db_query(self, query: str, *args):
        """Execute query with tenant isolation."""
        async with self.db_pool.acquire() as conn:
            # Set PostgreSQL context for RLS
            await TenantContext.set_postgres_context(conn)

            # Execute query (RLS automatically filters by tenant_id)
            return await conn.fetch(query, *args)
```

### API Authentication (Tenant Identification)

**File:** `api/middleware/auth.py`

```python
from fastapi import Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def authenticate_tenant(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> uuid.UUID:
    """
    Authenticate API request and return tenant_id.

    Uses bearer token: Authorization: Bearer sk_live_abc123...
    """
    api_key = credentials.credentials

    # Hash the provided key
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    # Look up tenant by hashed key
    async with db_pool.acquire() as conn:
        tenant = await conn.fetchrow(
            "SELECT id, status FROM tenants WHERE api_key_hash = $1",
            key_hash
        )

    if not tenant:
        # Log failed auth attempt (security event)
        await audit_log(event="auth_failed", ip=request.client.host)
        raise HTTPException(status_code=401, detail="Invalid API key")

    if tenant['status'] != 'active':
        raise HTTPException(status_code=403, detail="Account suspended")

    # Set tenant context for this request
    TenantContext.set_tenant(tenant['id'])

    return tenant['id']
```

### WebSocket Authentication (Twilio Calls)

**File:** `api/routes/voice_ws.py`

```python
@router.websocket("/ws/twilio")
async def twilio_websocket(websocket: WebSocket):
    await websocket.accept()

    # Receive initial "start" message from Twilio
    start_msg = await websocket.receive_json()

    # Extract tenant from call metadata
    # Twilio forwards custom headers as metadata
    custom_params = start_msg.get("start", {}).get("customParameters", {})
    tenant_slug = custom_params.get("tenant")

    if not tenant_slug:
        await websocket.close(code=1008, reason="Missing tenant")
        return

    # Look up tenant
    async with db_pool.acquire() as conn:
        tenant = await conn.fetchrow(
            "SELECT id, status FROM tenants WHERE slug = $1",
            tenant_slug
        )

    if not tenant or tenant['status'] != 'active':
        await websocket.close(code=1008, reason="Invalid tenant")
        return

    # Start voice session with tenant context
    async with VoiceSession(websocket, tenant_id=tenant['id']) as session:
        # ... handle call ...
```

---

## 3. Database Schema with Security

### Voice Sessions (with tenant isolation)

```sql
CREATE TABLE voice_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Session identifiers
    conversation_id TEXT UNIQUE NOT NULL,  -- OpenAI conversation ID
    call_sid TEXT UNIQUE,  -- Twilio call SID

    -- Captured data (notepad)
    notepad JSONB NOT NULL DEFAULT '{}',

    -- Transcript (optional, may be in S3 for large transcripts)
    transcript TEXT,
    transcript_s3_uri TEXT,  -- If too large for DB

    -- Metadata
    metadata JSONB DEFAULT '{}',
    duration_seconds INT,
    turn_count INT,

    -- Status
    status TEXT NOT NULL DEFAULT 'active',  -- active|completed|escalated|abandoned
    escalated BOOLEAN DEFAULT FALSE,
    escalation_reason TEXT,

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,

    -- Compliance
    data_deleted_at TIMESTAMP,  -- Soft delete for retention policy

    -- Indexes
    CONSTRAINT valid_status CHECK (status IN ('active', 'completed', 'escalated', 'abandoned'))
);

-- RLS
ALTER TABLE voice_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON voice_sessions
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Indexes
CREATE INDEX idx_sessions_tenant ON voice_sessions(tenant_id);
CREATE INDEX idx_sessions_created ON voice_sessions(created_at DESC);
CREATE INDEX idx_sessions_status ON voice_sessions(status);
CREATE INDEX idx_sessions_call_sid ON voice_sessions(call_sid);
```

### Customers (PII with field-level encryption)

```sql
CREATE TABLE customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- PII (encrypted at application level before storing)
    name_encrypted BYTEA NOT NULL,  -- AES-256-GCM encrypted
    phone_encrypted BYTEA NOT NULL,
    email_encrypted BYTEA,

    -- Hashed values for lookups (HMAC-SHA256)
    phone_hash TEXT NOT NULL,  -- For finding returning customers
    email_hash TEXT,

    -- Non-sensitive metadata
    total_reservations INT DEFAULT 0,
    last_reservation_at TIMESTAMP,

    -- Preferences (non-PII)
    dietary_restrictions TEXT[],  -- Could be PHI if specific medical conditions
    preferred_seating TEXT,

    -- Consent & compliance
    marketing_consent BOOLEAN DEFAULT FALSE,
    marketing_consent_date TIMESTAMP,
    data_processing_consent BOOLEAN NOT NULL DEFAULT TRUE,
    consent_ip_address INET,

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Soft delete for GDPR right to erasure
    deleted_at TIMESTAMP
);

-- RLS
ALTER TABLE customers ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON customers
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Indexes (only on hashed/non-encrypted fields!)
CREATE INDEX idx_customers_tenant ON customers(tenant_id);
CREATE INDEX idx_customers_phone_hash ON customers(phone_hash);
CREATE INDEX idx_customers_email_hash ON customers(email_hash);

-- Prevent accidental PII leaks in logs
COMMENT ON COLUMN customers.name_encrypted IS 'ENCRYPTED - Do not log';
COMMENT ON COLUMN customers.phone_encrypted IS 'ENCRYPTED - Do not log';
COMMENT ON COLUMN customers.email_encrypted IS 'ENCRYPTED - Do not log';
```

### Reservations

```sql
CREATE TABLE reservations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id UUID NOT NULL REFERENCES customers(id),
    session_id UUID REFERENCES voice_sessions(id),  -- Which call created this

    -- Reservation details
    reservation_date DATE NOT NULL,
    reservation_time TIME NOT NULL,
    party_size INT NOT NULL CHECK (party_size > 0 AND party_size <= 50),
    table_id TEXT,

    -- Special requests (could contain PHI - allergies)
    special_requests TEXT,

    -- Status
    status TEXT NOT NULL DEFAULT 'pending',  -- pending|confirmed|cancelled|no_show|completed

    -- Payment (PCI - use tokenization, NEVER store raw card numbers)
    payment_required BOOLEAN DEFAULT FALSE,
    payment_amount_cents INT,
    payment_token TEXT,  -- Stripe token, not raw card
    payment_status TEXT,  -- pending|authorized|captured|refunded

    -- Confirmation
    confirmation_code TEXT UNIQUE,  -- e.g., "RES-ABC123"
    confirmation_sent_at TIMESTAMP,

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    cancelled_at TIMESTAMP,

    CONSTRAINT valid_status CHECK (status IN ('pending', 'confirmed', 'cancelled', 'no_show', 'completed'))
);

-- RLS
ALTER TABLE reservations ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON reservations
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Indexes
CREATE INDEX idx_reservations_tenant ON reservations(tenant_id);
CREATE INDEX idx_reservations_date ON reservations(reservation_date);
CREATE INDEX idx_reservations_customer ON reservations(customer_id);
CREATE INDEX idx_reservations_confirmation ON reservations(confirmation_code);
```

### Audit Logs (Immutable)

```sql
CREATE TABLE audit_logs (
    id BIGSERIAL PRIMARY KEY,  -- Sequential, never deleted
    tenant_id UUID REFERENCES tenants(id),  -- NULL for system-wide events

    -- Event details
    event_type TEXT NOT NULL,  -- auth_success|auth_failed|data_access|data_modify|escalation
    actor_type TEXT NOT NULL,  -- system|user|agent|api
    actor_id TEXT,  -- User ID, API key hash, agent ID

    -- Context
    resource_type TEXT,  -- session|customer|reservation
    resource_id UUID,

    -- Action details
    action TEXT NOT NULL,  -- create|read|update|delete|export
    details JSONB DEFAULT '{}',

    -- Request metadata (for security investigations)
    ip_address INET NOT NULL,
    user_agent TEXT,
    request_id TEXT,

    -- Timestamp (microsecond precision)
    created_at TIMESTAMP(6) NOT NULL DEFAULT NOW(),

    -- Cryptographic signature (prevents tampering)
    signature TEXT NOT NULL
);

-- NO RLS on audit logs - separate access control
-- Only security team can query

-- Indexes
CREATE INDEX idx_audit_tenant ON audit_logs(tenant_id);
CREATE INDEX idx_audit_created ON audit_logs(created_at DESC);
CREATE INDEX idx_audit_event_type ON audit_logs(event_type);
CREATE INDEX idx_audit_actor ON audit_logs(actor_id);
CREATE INDEX idx_audit_resource ON audit_logs(resource_type, resource_id);

-- Prevent deletion
REVOKE DELETE ON audit_logs FROM public;
CREATE RULE no_delete_audit AS ON DELETE TO audit_logs DO INSTEAD NOTHING;
```

---

## 4. Encryption Strategy

### Encryption Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                     ENCRYPTION LAYERS                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. IN-TRANSIT (TLS 1.3)                                        │
│     • Client → Server: HTTPS, WSS (WebSocket Secure)            │
│     • Server → Database: TLS (required, reject non-TLS)         │
│     • Server → External APIs: TLS (Deepgram, OpenAI, Twilio)   │
│     • Internal services: mTLS (mutual TLS)                      │
│                                                                   │
│  2. AT-REST (Database)                                           │
│     • PostgreSQL: Transparent Data Encryption (TDE)             │
│     • Disk encryption: LUKS / AWS EBS encryption                │
│     • Backups: Encrypted before upload to S3                    │
│                                                                   │
│  3. FIELD-LEVEL (Application)                                    │
│     • PII fields: AES-256-GCM before INSERT                     │
│     • Encryption keys: Stored in KMS, rotated every 90 days    │
│     • Each tenant: Separate encryption key (data isolation)     │
│                                                                   │
│  4. OBJECT STORAGE (S3)                                          │
│     • Server-side encryption: AES-256 (SSE-S3 or SSE-KMS)      │
│     • Client-side encryption: For highly sensitive recordings   │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Field-Level Encryption Implementation

**File:** `services/crypto.py`

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend
import os
import base64
import hashlib

class FieldEncryption:
    """
    Field-level encryption for PII.

    Uses AES-256-GCM (authenticated encryption) with unique keys per tenant.
    Keys stored in KMS, cached in memory for performance.
    """

    def __init__(self, kms_client):
        self.kms = kms_client
        self.key_cache = {}  # tenant_id -> encryption key
        self.key_version = {}  # tenant_id -> version (for rotation)

    async def get_tenant_key(self, tenant_id: uuid.UUID) -> bytes:
        """Get encryption key for tenant from KMS."""
        if tenant_id in self.key_cache:
            return self.key_cache[tenant_id]

        # Fetch from KMS
        key_id = f"tenant-{tenant_id}-encryption-key"
        key_data = await self.kms.get_key(key_id)

        # Cache in memory (cleared on key rotation)
        self.key_cache[tenant_id] = key_data['key']
        self.key_version[tenant_id] = key_data['version']

        return key_data['key']

    async def encrypt(self, plaintext: str, tenant_id: uuid.UUID) -> bytes:
        """
        Encrypt plaintext using tenant's key.

        Format: [version:1][nonce:12][ciphertext][tag:16]
        """
        if not plaintext:
            return b''

        key = await self.get_tenant_key(tenant_id)
        aesgcm = AESGCM(key)

        # Generate random nonce (12 bytes for GCM)
        nonce = os.urandom(12)

        # Encrypt
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)

        # Pack: version (1 byte) + nonce (12 bytes) + ciphertext+tag
        version = self.key_version[tenant_id].to_bytes(1, 'big')
        return version + nonce + ciphertext

    async def decrypt(self, ciphertext: bytes, tenant_id: uuid.UUID) -> str:
        """Decrypt ciphertext using tenant's key."""
        if not ciphertext:
            return ''

        # Unpack: version + nonce + ciphertext
        version = int.from_bytes(ciphertext[0:1], 'big')
        nonce = ciphertext[1:13]
        encrypted = ciphertext[13:]

        # Get key (potentially old version if rotated)
        key = await self.get_tenant_key(tenant_id, version=version)
        aesgcm = AESGCM(key)

        # Decrypt
        plaintext_bytes = aesgcm.decrypt(nonce, encrypted, None)
        return plaintext_bytes.decode('utf-8')

    def hash_for_lookup(self, value: str, tenant_id: uuid.UUID) -> str:
        """
        Create HMAC hash for lookup (e.g., phone number search).

        Cannot be reversed, but can be compared.
        Uses tenant-specific salt to prevent rainbow tables.
        """
        salt = f"lookup-salt-{tenant_id}"
        return hashlib.sha256(f"{salt}:{value}".encode()).hexdigest()
```

### Usage in Data Access Layer

```python
class CustomerRepository:
    def __init__(self, crypto: FieldEncryption):
        self.crypto = crypto

    async def create_customer(
        self,
        tenant_id: uuid.UUID,
        name: str,
        phone: str,
        email: str | None
    ) -> uuid.UUID:
        """Create customer with encrypted PII."""

        # Encrypt PII fields
        name_encrypted = await self.crypto.encrypt(name, tenant_id)
        phone_encrypted = await self.crypto.encrypt(phone, tenant_id)
        email_encrypted = await self.crypto.encrypt(email, tenant_id) if email else None

        # Hash for lookups
        phone_hash = self.crypto.hash_for_lookup(phone, tenant_id)
        email_hash = self.crypto.hash_for_lookup(email, tenant_id) if email else None

        # Insert
        async with db_pool.acquire() as conn:
            await TenantContext.set_postgres_context(conn)

            customer_id = await conn.fetchval(
                """
                INSERT INTO customers (
                    tenant_id, name_encrypted, phone_encrypted, email_encrypted,
                    phone_hash, email_hash
                ) VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                tenant_id, name_encrypted, phone_encrypted, email_encrypted,
                phone_hash, email_hash
            )

        # Audit log
        await audit_log(
            event_type="customer_created",
            actor_type="system",
            resource_type="customer",
            resource_id=customer_id,
            tenant_id=tenant_id
        )

        return customer_id

    async def get_customer(self, customer_id: uuid.UUID) -> dict:
        """Get customer with decrypted PII."""
        tenant_id = TenantContext.get_tenant()

        async with db_pool.acquire() as conn:
            await TenantContext.set_postgres_context(conn)

            row = await conn.fetchrow(
                "SELECT * FROM customers WHERE id = $1",
                customer_id
            )

        if not row:
            return None

        # Decrypt PII
        return {
            "id": row['id'],
            "name": await self.crypto.decrypt(row['name_encrypted'], tenant_id),
            "phone": await self.crypto.decrypt(row['phone_encrypted'], tenant_id),
            "email": await self.crypto.decrypt(row['email_encrypted'], tenant_id) if row['email_encrypted'] else None,
            "created_at": row['created_at']
        }

    async def find_by_phone(self, phone: str) -> dict | None:
        """Find customer by phone (uses hashed lookup)."""
        tenant_id = TenantContext.get_tenant()
        phone_hash = self.crypto.hash_for_lookup(phone, tenant_id)

        async with db_pool.acquire() as conn:
            await TenantContext.set_postgres_context(conn)

            row = await conn.fetchrow(
                "SELECT * FROM customers WHERE phone_hash = $1",
                phone_hash
            )

        if not row:
            return None

        return await self.get_customer(row['id'])
```

---

## 5. Access Control & Authentication

### Role-Based Access Control (RBAC)

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),

    email TEXT NOT NULL,
    password_hash TEXT NOT NULL,  -- bcrypt with cost 12

    role TEXT NOT NULL,  -- admin|manager|agent|readonly

    -- MFA
    mfa_enabled BOOLEAN DEFAULT FALSE,
    mfa_secret TEXT,  -- TOTP secret (encrypted)

    -- Status
    active BOOLEAN DEFAULT TRUE,
    locked_until TIMESTAMP,  -- Account lockout after failed logins
    last_login_at TIMESTAMP,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    UNIQUE(tenant_id, email)
);

-- Permissions per role
CREATE TABLE role_permissions (
    role TEXT PRIMARY KEY,
    permissions JSONB NOT NULL
);

INSERT INTO role_permissions VALUES
('admin', '{
    "sessions": ["create", "read", "update", "delete"],
    "customers": ["create", "read", "update", "delete", "export"],
    "reservations": ["create", "read", "update", "delete"],
    "agents": ["create", "read", "update", "delete"],
    "settings": ["read", "update"]
}'::jsonb),

('manager', '{
    "sessions": ["read"],
    "customers": ["read", "export"],
    "reservations": ["create", "read", "update"],
    "agents": ["read"],
    "settings": ["read"]
}'::jsonb),

('agent', '{
    "sessions": ["read"],
    "customers": ["read"],
    "reservations": ["read", "update"]
}'::jsonb),

('readonly', '{
    "sessions": ["read"],
    "customers": ["read"],
    "reservations": ["read"]
}'::jsonb);
```

### Permission Checking

**File:** `services/authz.py`

```python
class AuthorizationService:
    """Check permissions based on RBAC."""

    async def check_permission(
        self,
        user_id: uuid.UUID,
        resource: str,
        action: str
    ) -> bool:
        """
        Check if user has permission for action on resource.

        Example: check_permission(user_id, "customers", "export")
        """
        async with db_pool.acquire() as conn:
            perms = await conn.fetchval(
                """
                SELECT p.permissions
                FROM users u
                JOIN role_permissions p ON u.role = p.role
                WHERE u.id = $1 AND u.active = TRUE
                """,
                user_id
            )

        if not perms:
            return False

        resource_perms = perms.get(resource, [])
        return action in resource_perms

    async def require_permission(
        self,
        user_id: uuid.UUID,
        resource: str,
        action: str
    ) -> None:
        """Raise exception if user lacks permission."""
        if not await self.check_permission(user_id, resource, action):
            # Audit log
            await audit_log(
                event_type="permission_denied",
                actor_type="user",
                actor_id=str(user_id),
                details={"resource": resource, "action": action}
            )

            raise PermissionDenied(f"User lacks permission: {resource}.{action}")
```

### API Endpoint Protection

```python
from fastapi import Depends

async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Dependency: require admin role."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    return user

@router.get("/customers/export")
async def export_customers(
    user: User = Depends(require_admin),
    authz: AuthorizationService = Depends()
):
    """Export customer data (admin only, requires 'export' permission)."""
    await authz.require_permission(user.id, "customers", "export")

    # Audit log
    await audit_log(
        event_type="data_export",
        actor_type="user",
        actor_id=str(user.id),
        resource_type="customers",
        details={"export_type": "csv"}
    )

    # ... perform export ...
```

---

## 6. Secrets Management

### Never Store Secrets in Code or Environment Variables

**❌ BAD:**
```python
DEEPGRAM_API_KEY = "abc123..."  # NEVER
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]  # Logged in env dumps
```

**✅ GOOD:**
```python
# Fetch from secrets manager at runtime
deepgram_key = await secrets_manager.get_secret("prod/voice-ai/deepgram-api-key")
```

### Secrets Manager Integration

**File:** `services/secrets.py`

```python
import boto3
import json
from functools import lru_cache

class SecretsManager:
    """
    Secrets management using AWS Secrets Manager.

    Alternatives: HashiCorp Vault, GCP Secret Manager, Azure Key Vault
    """

    def __init__(self, region: str = "us-east-1"):
        self.client = boto3.client('secretsmanager', region_name=region)
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes

    async def get_secret(self, secret_id: str) -> str:
        """
        Get secret from AWS Secrets Manager (cached).

        Example: await get_secret("prod/voice-ai/deepgram-api-key")
        """
        if secret_id in self.cache:
            cached_at, value = self.cache[secret_id]
            if time.time() - cached_at < self.cache_ttl:
                return value

        # Fetch from AWS
        response = self.client.get_secret_value(SecretId=secret_id)

        if 'SecretString' in response:
            secret = response['SecretString']
        else:
            secret = base64.b64decode(response['SecretBinary']).decode()

        # Cache
        self.cache[secret_id] = (time.time(), secret)

        return secret

    async def get_secret_json(self, secret_id: str) -> dict:
        """Get secret and parse as JSON."""
        secret_str = await self.get_secret(secret_id)
        return json.loads(secret_str)

    async def rotate_secret(self, secret_id: str, new_value: str) -> None:
        """Rotate a secret (e.g., API key)."""
        self.client.update_secret(
            SecretId=secret_id,
            SecretString=new_value
        )

        # Clear cache
        if secret_id in self.cache:
            del self.cache[secret_id]

        # Audit log
        await audit_log(
            event_type="secret_rotated",
            actor_type="system",
            details={"secret_id": secret_id}
        )
```

### Usage in Providers

**File:** `providers/stt/deepgram.py`

```python
from voice_ai.services.secrets import SecretsManager

class DeepgramSTT:
    def __init__(self, secrets: SecretsManager):
        self.secrets = secrets
        self._client = None

    async def _get_client(self):
        """Lazy-load client with API key from secrets manager."""
        if self._client is None:
            api_key = await self.secrets.get_secret("prod/voice-ai/deepgram-api-key")
            self._client = AsyncDeepgramClient(api_key=api_key)
        return self._client

    async def transcribe_stream(self, ...):
        client = await self._get_client()
        # ... use client ...
```

### Secret Rotation Policy

| Secret Type | Rotation Frequency | Auto-Rotation | Notification |
|-------------|-------------------|---------------|--------------|
| Database credentials | 90 days | Yes | Email + Slack |
| API keys (external) | Manual (on breach) | No | N/A |
| Encryption keys (KMS) | 365 days | Yes | Email |
| JWT signing keys | 180 days | Yes | Auto |
| TLS certificates | 365 days | Yes (Let's Encrypt) | Auto |

---

## 7. Network Security

### Network Topology

```
┌─────────────────────────────────────────────────────────────────┐
│                      NETWORK ARCHITECTURE                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  INTERNET                                                        │
│     ↓                                                            │
│  ┌──────────────────────────────────────┐                      │
│  │  CDN / DDoS Protection (Cloudflare)  │                      │
│  │  - Rate limiting: 100 req/sec/IP     │                      │
│  │  - Bot detection                      │                      │
│  │  - TLS termination (1.3 only)        │                      │
│  └──────────────────────────────────────┘                      │
│     ↓                                                            │
│  ┌──────────────────────────────────────┐                      │
│  │  Load Balancer (AWS ALB / NGINX)     │                      │
│  │  - SSL/TLS offloading                 │                      │
│  │  - Health checks                      │                      │
│  │  - Request logging                    │                      │
│  └──────────────────────────────────────┘                      │
│     ↓                                                            │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  PUBLIC SUBNET (DMZ)                                      │ │
│  │                                                            │ │
│  │  ┌────────────────────────────────────┐                  │ │
│  │  │  API Servers (FastAPI)             │                  │ │
│  │  │  - No database credentials         │                  │ │
│  │  │  - Fetch secrets from KMS          │                  │ │
│  │  │  - Outbound only to private subnet │                  │ │
│  │  └────────────────────────────────────┘                  │ │
│  │                                                            │ │
│  └──────────────────────────────────────────────────────────┘ │
│     ↓ (Private connection only)                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  PRIVATE SUBNET (No internet access)                      │ │
│  │                                                            │ │
│  │  ┌────────────────────────────────────┐                  │ │
│  │  │  PostgreSQL (Primary + Replicas)   │                  │ │
│  │  │  - No public IP                    │                  │ │
│  │  │  - TLS required                     │                  │ │
│  │  │  - IP whitelist (API servers only) │                  │ │
│  │  └────────────────────────────────────┘                  │ │
│  │                                                            │ │
│  │  ┌────────────────────────────────────┐                  │ │
│  │  │  Redis (Cluster mode)               │                  │ │
│  │  │  - TLS enabled                      │                  │ │
│  │  │  - AUTH password required           │                  │ │
│  │  └────────────────────────────────────┘                  │ │
│  │                                                            │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                   │
│  Egress (API servers → external APIs):                          │
│    - Deepgram: TLS 1.3, API key in headers                     │
│    - OpenAI: TLS 1.3, API key in headers                       │
│    - Twilio: TLS 1.3, webhook signature verification          │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Firewall Rules

```bash
# Security Groups (AWS) / Firewall Rules

# Public Subnet (API servers)
Inbound:
  - Port 443 (HTTPS) from Cloudflare IPs only
  - Port 22 (SSH) from bastion host only (for maintenance)

Outbound:
  - Port 443 (HTTPS) to anywhere (external APIs)
  - Port 5432 (PostgreSQL) to private subnet only
  - Port 6379 (Redis) to private subnet only

# Private Subnet (Database)
Inbound:
  - Port 5432 from public subnet (API servers) only
  - Port 6379 from public subnet (API servers) only

Outbound:
  - DENY all (no internet access)
```

### Rate Limiting

**File:** `api/middleware/rate_limit.py`

```python
from fastapi import Request, HTTPException
from redis import asyncio as aioredis

class RateLimiter:
    """Token bucket rate limiter using Redis."""

    def __init__(self, redis: aioredis.Redis):
        self.redis = redis

    async def check_rate_limit(
        self,
        request: Request,
        limit: int = 100,  # Requests per window
        window: int = 60   # Window in seconds
    ) -> None:
        """
        Check if request exceeds rate limit.

        Raises HTTPException(429) if rate limited.
        """
        # Key: IP address or API key
        identifier = request.client.host

        # Check if authenticated (use tenant_id for keying)
        if hasattr(request.state, 'tenant_id'):
            identifier = str(request.state.tenant_id)

        key = f"ratelimit:{identifier}:{int(time.time() // window)}"

        # Increment counter
        count = await self.redis.incr(key)

        if count == 1:
            # Set expiry on first request in window
            await self.redis.expire(key, window)

        if count > limit:
            # Log rate limit event
            await audit_log(
                event_type="rate_limit_exceeded",
                actor_type="api",
                actor_id=identifier,
                ip_address=request.client.host
            )

            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Try again in {window} seconds."
            )
```

---

## 8. Compliance Requirements

### GDPR (General Data Protection Regulation)

**Applies to:** EU customers

**Requirements:**
1. ✅ **Right to Access** - Users can request their data
2. ✅ **Right to Erasure** - Delete user data on request ("right to be forgotten")
3. ✅ **Right to Portability** - Export data in machine-readable format
4. ✅ **Consent Management** - Explicit consent for data processing
5. ✅ **Data Minimization** - Only collect necessary data
6. ✅ **Breach Notification** - Notify within 72 hours of breach

**Implementation:**

```python
@router.post("/gdpr/data-request")
async def gdpr_data_request(
    customer_email: str,
    tenant_id: uuid.UUID = Depends(authenticate_tenant)
):
    """
    GDPR Article 15: Right to Access

    User requests all data associated with their email.
    """
    # Find customer
    customer = await customer_repo.find_by_email(customer_email)

    if not customer:
        raise HTTPException(404, "Customer not found")

    # Collect all data
    sessions = await db.fetch(
        "SELECT * FROM voice_sessions WHERE notepad->>'email' = $1",
        customer_email
    )

    reservations = await db.fetch(
        "SELECT * FROM reservations WHERE customer_id = $1",
        customer['id']
    )

    # Export as JSON
    export = {
        "customer": customer,
        "sessions": [dict(s) for s in sessions],
        "reservations": [dict(r) for r in reservations],
        "exported_at": datetime.utcnow().isoformat()
    }

    # Audit log
    await audit_log(
        event_type="gdpr_data_access",
        actor_type="user",
        resource_id=customer['id'],
        tenant_id=tenant_id
    )

    return export

@router.delete("/gdpr/delete-data")
async def gdpr_delete_data(
    customer_email: str,
    tenant_id: uuid.UUID = Depends(authenticate_tenant)
):
    """
    GDPR Article 17: Right to Erasure

    Delete all customer data (irreversible).
    """
    customer = await customer_repo.find_by_email(customer_email)

    if not customer:
        raise HTTPException(404, "Customer not found")

    # Soft delete (mark as deleted, actual erasure after 30 days)
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE customers SET deleted_at = NOW() WHERE id = $1",
            customer['id']
        )

        # Anonymize sessions (remove PII, keep analytics)
        await conn.execute(
            """
            UPDATE voice_sessions
            SET notepad = '{"anonymized": true}'::jsonb,
                transcript = '[REDACTED]'
            WHERE conversation_id IN (
                SELECT conversation_id FROM voice_sessions
                WHERE notepad->>'email' = $1
            )
            """,
            customer_email
        )

    # Delete recordings from S3
    await s3.delete_objects_by_prefix(f"recordings/{customer['id']}/")

    # Audit log (immutable, preserved even after deletion)
    await audit_log(
        event_type="gdpr_data_deletion",
        actor_type="user",
        resource_id=customer['id'],
        tenant_id=tenant_id
    )

    return {"status": "deleted", "customer_id": customer['id']}
```

### HIPAA (Health Insurance Portability and Accountability Act)

**Applies to:** If handling health data (allergies, medical dietary restrictions)

**Requirements:**
1. ✅ **Encryption** - At rest (AES-256) and in transit (TLS 1.2+)
2. ✅ **Access Controls** - Role-based access, audit logs
3. ✅ **Audit Trail** - Complete history of who accessed PHI
4. ✅ **Business Associate Agreements (BAA)** - With Deepgram, OpenAI, Twilio
5. ✅ **Breach Notification** - Notify affected users + HHS within 60 days
6. ✅ **Data Retention** - 6 years minimum

**PHI Identification:**

```python
# Mark fields containing PHI
PHI_FIELDS = [
    "customers.name_encrypted",
    "customers.phone_encrypted",
    "customers.email_encrypted",
    "customers.dietary_restrictions",  # Could be PHI if medical
    "reservations.special_requests"    # Could contain medical info
]

# Extra access controls for PHI
async def access_phi(user: User, customer_id: uuid.UUID):
    """Access PHI with extra audit logging."""
    # Require specific permission
    await authz.require_permission(user.id, "customers", "access_phi")

    # Log PHI access (detailed)
    await audit_log(
        event_type="phi_access",
        actor_type="user",
        actor_id=str(user.id),
        resource_type="customer",
        resource_id=customer_id,
        details={
            "reason": "reservation_modification",
            "fields_accessed": ["dietary_restrictions"]
        }
    )

    # ... perform access ...
```

### PCI-DSS (Payment Card Industry Data Security Standard)

**Applies to:** If storing payment information

**Solution: DON'T STORE PAYMENT DATA**

Use tokenization (Stripe, Square):

```python
@router.post("/reservations/{id}/payment")
async def capture_payment(
    reservation_id: uuid.UUID,
    payment_token: str,  # Stripe token, not raw card
    tenant_id: uuid.UUID = Depends(authenticate_tenant)
):
    """
    Capture payment for reservation.

    NEVER send raw card numbers to our backend.
    Use Stripe.js to tokenize on client side.
    """
    import stripe

    reservation = await reservations_repo.get(reservation_id)

    # Charge via Stripe (they handle PCI compliance)
    charge = stripe.Charge.create(
        amount=reservation['payment_amount_cents'],
        currency="usd",
        source=payment_token,  # Token from Stripe.js
        description=f"Reservation {reservation['confirmation_code']}"
    )

    # Store ONLY the charge ID (not card details)
    await db.execute(
        """
        UPDATE reservations
        SET payment_token = $1, payment_status = 'captured'
        WHERE id = $2
        """,
        charge.id,  # Stripe charge ID (safe to store)
        reservation_id
    )

    # Audit log
    await audit_log(
        event_type="payment_captured",
        resource_type="reservation",
        resource_id=reservation_id,
        details={"amount_cents": reservation['payment_amount_cents']}
    )

    return {"status": "captured", "charge_id": charge.id}
```

### SOC 2 Type II (For Enterprise Customers)

**Requirements:**
1. ✅ **Security** - Access controls, encryption, monitoring
2. ✅ **Availability** - 99.9% uptime, redundancy, backups
3. ✅ **Processing Integrity** - Data validation, error handling
4. ✅ **Confidentiality** - NDA, tenant isolation
5. ✅ **Privacy** - GDPR/CCPA compliance, consent management

**Annual audit by third-party auditor required.**

---

## 9. Audit & Monitoring

### Audit Logging (All Events)

```python
async def audit_log(
    event_type: str,
    actor_type: str,
    actor_id: str | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    ip_address: str | None = None,
    details: dict | None = None
) -> None:
    """
    Log security-relevant event to audit trail.

    All events are immutable and cannot be deleted.
    """
    # Get request context if available
    if ip_address is None and hasattr(contextvars, 'request'):
        request = contextvars.request.get()
        ip_address = request.client.host

    # Create cryptographic signature (HMAC)
    event_data = {
        "event_type": event_type,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "resource_type": resource_type,
        "resource_id": str(resource_id) if resource_id else None,
        "tenant_id": str(tenant_id) if tenant_id else None,
        "timestamp": time.time()
    }

    signature = hmac.new(
        AUDIT_LOG_SECRET.encode(),
        json.dumps(event_data, sort_keys=True).encode(),
        hashlib.sha256
    ).hexdigest()

    # Insert (never update, never delete)
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO audit_logs (
                tenant_id, event_type, actor_type, actor_id,
                resource_type, resource_id, details,
                ip_address, signature
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            tenant_id, event_type, actor_type, actor_id,
            resource_type, resource_id, json.dumps(details or {}),
            ip_address, signature
        )
```

### Events to Audit

| Event Type | When | Who | Why |
|------------|------|-----|-----|
| `auth_success` | User logs in | User | Track access patterns |
| `auth_failed` | Login fails | User | Detect brute force |
| `data_access` | PHI/PII read | User/Agent | HIPAA/GDPR requirement |
| `data_modify` | Data updated | User/Agent | Track changes |
| `data_export` | Data exported | Admin | Sensitive operation |
| `permission_denied` | Access denied | User | Detect unauthorized attempts |
| `escalation` | Call escalated | System | Business metric |
| `payment_captured` | Payment processed | System | Financial audit |
| `secret_rotated` | API key changed | Admin | Security event |
| `gdpr_data_access` | User requests data | User | Legal requirement |
| `gdpr_data_deletion` | User deleted | User | Legal requirement |

### Security Monitoring (Real-Time Alerts)

```python
# File: services/security_monitor.py

class SecurityMonitor:
    """Real-time security threat detection."""

    async def check_failed_logins(self, user_id: uuid.UUID):
        """Alert on 5 failed logins in 5 minutes."""
        count = await db.fetchval(
            """
            SELECT COUNT(*)
            FROM audit_logs
            WHERE event_type = 'auth_failed'
              AND actor_id = $1
              AND created_at > NOW() - INTERVAL '5 minutes'
            """,
            str(user_id)
        )

        if count >= 5:
            await self.alert(
                severity="high",
                message=f"Multiple failed logins for user {user_id}",
                action="lock_account"
            )

    async def check_mass_export(self, tenant_id: uuid.UUID):
        """Alert on large data exports (possible breach)."""
        count = await db.fetchval(
            """
            SELECT COUNT(*)
            FROM audit_logs
            WHERE event_type = 'data_export'
              AND tenant_id = $1
              AND created_at > NOW() - INTERVAL '1 hour'
            """,
            tenant_id
        )

        if count > 10:
            await self.alert(
                severity="critical",
                message=f"Mass data export detected for tenant {tenant_id}",
                action="require_reauth"
            )

    async def alert(self, severity: str, message: str, action: str):
        """Send alert to security team."""
        # Log to audit
        await audit_log(
            event_type="security_alert",
            actor_type="system",
            details={"severity": severity, "message": message, "action": action}
        )

        # Send to PagerDuty / Slack
        if severity == "critical":
            await pagerduty.trigger(message)
        else:
            await slack.send_alert(message)
```

---

## 10. Data Retention & Deletion

### Retention Policies

```sql
CREATE TABLE retention_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),

    -- Policy settings
    data_type TEXT NOT NULL,  -- sessions|recordings|transcripts|reservations
    retention_days INT NOT NULL,

    -- Deletion method
    deletion_method TEXT NOT NULL,  -- soft_delete|hard_delete|anonymize

    -- Status
    enabled BOOLEAN DEFAULT TRUE,
    last_run_at TIMESTAMP,

    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Default policies (insert on tenant creation)
INSERT INTO retention_policies (tenant_id, data_type, retention_days, deletion_method)
VALUES
    (tenant_id, 'sessions', 365, 'anonymize'),  -- Keep 1 year, then anonymize
    (tenant_id, 'recordings', 90, 'hard_delete'),  -- Keep 90 days, then delete
    (tenant_id, 'transcripts', 365, 'soft_delete'),  -- Soft delete after 1 year
    (tenant_id, 'reservations', 2555, 'soft_delete');  -- 7 years (legal requirement)
```

### Automated Cleanup Job

```python
# File: jobs/data_retention.py

import asyncio
from datetime import datetime, timedelta

async def run_retention_cleanup():
    """
    Run data retention cleanup (daily cron job).

    Deletes/anonymizes data based on tenant retention policies.
    """
    policies = await db.fetch("SELECT * FROM retention_policies WHERE enabled = TRUE")

    for policy in policies:
        tenant_id = policy['tenant_id']
        data_type = policy['data_type']
        retention_days = policy['retention_days']
        deletion_method = policy['deletion_method']

        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

        if data_type == 'sessions':
            if deletion_method == 'anonymize':
                # Anonymize old sessions (remove PII, keep analytics)
                count = await db.execute(
                    """
                    UPDATE voice_sessions
                    SET notepad = '{"anonymized": true}'::jsonb,
                        transcript = '[REDACTED]',
                        data_deleted_at = NOW()
                    WHERE tenant_id = $1
                      AND created_at < $2
                      AND data_deleted_at IS NULL
                    """,
                    tenant_id, cutoff_date
                )
                logger.info(f"Anonymized {count} sessions for tenant {tenant_id}")

        elif data_type == 'recordings':
            if deletion_method == 'hard_delete':
                # Delete recordings from S3
                sessions = await db.fetch(
                    """
                    SELECT id FROM voice_sessions
                    WHERE tenant_id = $1
                      AND created_at < $2
                      AND data_deleted_at IS NULL
                    """,
                    tenant_id, cutoff_date
                )

                for session in sessions:
                    s3_key = f"recordings/{tenant_id}/{session['id']}.wav"
                    await s3.delete_object(bucket="voice-ai-recordings", key=s3_key)

                logger.info(f"Deleted {len(sessions)} recordings for tenant {tenant_id}")

        # Update last run
        await db.execute(
            "UPDATE retention_policies SET last_run_at = NOW() WHERE id = $1",
            policy['id']
        )

        # Audit log
        await audit_log(
            event_type="retention_cleanup",
            actor_type="system",
            tenant_id=tenant_id,
            details={
                "data_type": data_type,
                "cutoff_date": cutoff_date.isoformat(),
                "count": count
            }
        )

# Run daily at 2am UTC
if __name__ == "__main__":
    asyncio.run(run_retention_cleanup())
```

---

## 11. Backup & Disaster Recovery

### Backup Strategy (3-2-1 Rule)

- **3 copies** of data (production + 2 backups)
- **2 different media** (disk + S3)
- **1 offsite** (cross-region replication)

### PostgreSQL Backups

```bash
#!/bin/bash
# Automated daily backup script

# Configuration
DB_HOST="prod-db.internal"
DB_NAME="voice_ai"
BACKUP_DIR="/backups/postgres"
S3_BUCKET="voice-ai-backups"
RETENTION_DAYS=30

# Create backup
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/voice_ai_$TIMESTAMP.sql.gz"

pg_dump -h $DB_HOST -U postgres $DB_NAME | gzip > $BACKUP_FILE

# Encrypt before upload
gpg --encrypt --recipient backup@company.com $BACKUP_FILE

# Upload to S3 (cross-region)
aws s3 cp $BACKUP_FILE.gpg s3://$S3_BUCKET/ --region us-west-2

# Delete local backup after upload
rm $BACKUP_FILE $BACKUP_FILE.gpg

# Delete old backups (retention policy)
find $BACKUP_DIR -name "*.sql.gz" -mtime +$RETENTION_DAYS -delete
aws s3 ls s3://$S3_BUCKET/ | awk '{print $4}' | xargs -I {} aws s3 rm s3://$S3_BUCKET/{}
```

### Disaster Recovery Plan

**RTO (Recovery Time Objective):** 4 hours
**RPO (Recovery Point Objective):** 1 hour (continuous WAL archiving)

**DR Steps:**

1. **Database Failure**
   - Promote read replica to primary (automated, 2 minutes)
   - Update DNS to point to new primary
   - Verify data integrity

2. **Full Region Failure**
   - Restore from S3 backup to new region
   - Restore latest WAL files (point-in-time recovery)
   - Redirect traffic via Route53

3. **Data Corruption**
   - Restore from latest clean backup
   - Replay WAL logs up to corruption point
   - Manual verification by DBA

**Testing:** Run DR drill quarterly.

---

## 12. Policy Storage & Management

### Where Policies Live

**Policies = Business Rules**

Examples:
- "Free plan gets 100 calls/month"
- "No reservations for parties > 20"
- "Cancellation allowed up to 2 hours before"
- "Dietary restrictions must be captured"

### Option 1: Database (Dynamic Policies) ✅ RECOMMENDED

**Pros:** Can be updated without code deployment, per-tenant customization

```sql
CREATE TABLE business_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),  -- NULL = global policy

    policy_type TEXT NOT NULL,  -- reservation|payment|escalation|feature_flag
    policy_key TEXT NOT NULL,  -- max_party_size|cancellation_window_hours
    policy_value JSONB NOT NULL,

    enabled BOOLEAN DEFAULT TRUE,
    priority INT DEFAULT 0,  -- Higher priority overrides lower

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    UNIQUE(tenant_id, policy_type, policy_key)
);

-- Example policies
INSERT INTO business_policies (tenant_id, policy_type, policy_key, policy_value) VALUES
(NULL, 'reservation', 'max_party_size', '20'),  -- Global: max 20 people
(tenant_id_1, 'reservation', 'max_party_size', '50'),  -- Tenant override: max 50
(NULL, 'reservation', 'cancellation_window_hours', '2'),  -- Must cancel 2hrs before
(NULL, 'escalation', 'auto_escalate_after_turns', '5'),  -- Escalate after 5 turns if incomplete
(tenant_id_2, 'feature_flag', 'rag_enabled', 'true');  -- Enable RAG for tenant
```

**Usage:**

```python
class PolicyService:
    """Query business policies."""

    async def get_policy(
        self,
        policy_type: str,
        policy_key: str,
        tenant_id: uuid.UUID | None = None
    ) -> Any:
        """
        Get policy value (tenant-specific overrides global).

        Example: await get_policy("reservation", "max_party_size", tenant_id)
        """
        # Try tenant-specific first
        if tenant_id:
            row = await db.fetchrow(
                """
                SELECT policy_value
                FROM business_policies
                WHERE tenant_id = $1
                  AND policy_type = $2
                  AND policy_key = $3
                  AND enabled = TRUE
                ORDER BY priority DESC
                LIMIT 1
                """,
                tenant_id, policy_type, policy_key
            )
            if row:
                return row['policy_value']

        # Fall back to global policy
        row = await db.fetchrow(
            """
            SELECT policy_value
            FROM business_policies
            WHERE tenant_id IS NULL
              AND policy_type = $2
              AND policy_key = $3
              AND enabled = TRUE
            ORDER BY priority DESC
            LIMIT 1
            """,
            policy_type, policy_key
        )

        return row['policy_value'] if row else None
```

### Option 2: Code (Static Policies)

**Pros:** Type-safe, versioned in Git, fast (no DB query)

```python
# File: voice_ai/policies.py

@dataclass
class ReservationPolicies:
    max_party_size: int = 20
    min_advance_hours: int = 1  # Must book at least 1 hour in advance
    cancellation_window_hours: int = 2
    require_phone: bool = True
    require_email: bool = False

@dataclass
class EscalationPolicies:
    auto_escalate_after_turns: int = 5
    auto_escalate_if_incomplete: bool = True
    escalate_on_frustration: bool = True

# Per-tenant overrides (could be in DB)
TENANT_POLICY_OVERRIDES = {
    "enterprise-restaurant": {
        "reservation": {"max_party_size": 100},
        "escalation": {"auto_escalate_after_turns": 3}
    }
}
```

### Option 3: External Config Service (Microservices)

**For large deployments:** Use LaunchDarkly, Split.io for feature flags

```python
from launchdarkly import LDClient

client = LDClient(sdk_key="sdk-xxx")

# Check feature flag
if client.variation("rag_enabled", {"key": tenant_id}, False):
    context = await rag.get_context(...)
```

### Recommendation: **Database for business policies, Code for security policies**

---

## 13. Deployment Architecture

### Production Infrastructure (AWS Example)

```
┌─────────────────────────────────────────────────────────────────┐
│                   PRODUCTION DEPLOYMENT (AWS)                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  REGION: us-east-1 (Primary)                                    │
│  ├── VPC: 10.0.0.0/16                                           │
│  │   ├── Public Subnet (10.0.1.0/24) - AZ-A                    │
│  │   │   ├── ALB (Application Load Balancer)                    │
│  │   │   └── NAT Gateway                                        │
│  │   │                                                           │
│  │   ├── Private Subnet (10.0.10.0/24) - AZ-A                  │
│  │   │   ├── ECS Fargate (API servers) - Auto-scaling 2-10     │
│  │   │   ├── RDS PostgreSQL 15 (Primary) - db.r6g.xlarge      │
│  │   │   └── ElastiCache Redis 7 (Cluster) - 3 nodes           │
│  │   │                                                           │
│  │   └── Private Subnet (10.0.11.0/24) - AZ-B (Failover)       │
│  │       ├── ECS Fargate (API servers) - Standby               │
│  │       └── RDS PostgreSQL 15 (Read Replica)                  │
│  │                                                               │
│  ├── S3 Buckets                                                  │
│  │   ├── voice-ai-recordings (Encrypted, versioning)           │
│  │   ├── voice-ai-backups (Cross-region replication)           │
│  │   └── voice-ai-logs (Lifecycle: delete after 90 days)       │
│  │                                                               │
│  ├── Secrets Manager                                             │
│  │   ├── prod/voice-ai/deepgram-api-key                        │
│  │   ├── prod/voice-ai/openai-api-key                          │
│  │   ├── prod/voice-ai/db-password (rotated every 90 days)    │
│  │   └── prod/voice-ai/encryption-keys (per tenant)            │
│  │                                                               │
│  ├── CloudWatch (Monitoring)                                    │
│  │   ├── Logs: /aws/ecs/voice-ai-api                           │
│  │   ├── Metrics: API latency, error rate, DB connections      │
│  │   └── Alarms: → SNS → PagerDuty                            │
│  │                                                               │
│  └── Route53 (DNS)                                              │
│      └── api.voice-ai.com → ALB                                 │
│                                                                   │
│  REGION: us-west-2 (Disaster Recovery)                          │
│  └── RDS PostgreSQL (Cross-region read replica)                 │
│  └── S3 (Cross-region replication destination)                  │
│                                                                   │
│  EXTERNAL SERVICES                                               │
│  ├── Cloudflare (CDN, DDoS protection, WAF)                    │
│  ├── Datadog (APM, Log aggregation)                             │
│  ├── Sentry (Error tracking)                                    │
│  └── PagerDuty (On-call alerting)                              │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Environment Separation

| Environment | Purpose | Data | Secrets | Monitoring |
|-------------|---------|------|---------|------------|
| **Production** | Live customer calls | Real PII | AWS Secrets Manager | Full (24/7) |
| **Staging** | Pre-release testing | Anonymized copy | Separate vault | Full |
| **Development** | Feature development | Synthetic data | `.env` file (local only) | Basic |
| **CI/CD** | Automated tests | Fixtures | GitHub Secrets | Test results only |

**Never use production data in dev/staging.**

---

## Summary: Security Checklist

### Before Going to Production

- [ ] **Multi-tenant isolation:** RLS enabled on all tables
- [ ] **Encryption:** TLS 1.3 in transit, AES-256 at rest
- [ ] **Field-level encryption:** PII encrypted in database
- [ ] **Secrets management:** No hardcoded keys, use vault
- [ ] **Access control:** RBAC implemented, roles defined
- [ ] **Audit logging:** All sensitive operations logged (immutable)
- [ ] **Rate limiting:** 100 req/sec per tenant
- [ ] **GDPR compliance:** Data export + deletion endpoints
- [ ] **Data retention:** Automated cleanup based on policy
- [ ] **Backups:** Daily encrypted backups to S3 (cross-region)
- [ ] **Disaster recovery:** DR plan documented, tested quarterly
- [ ] **Network security:** Private subnet for DB, no public IPs
- [ ] **Monitoring:** CloudWatch alarms for errors, latency, security events
- [ ] **Penetration testing:** Annual pentest by third party
- [ ] **SOC 2 audit:** If enterprise customers (annual)
- [ ] **BAAs signed:** Deepgram, OpenAI, Twilio (if HIPAA)

---

## Key Takeaways

1. **Multi-tenancy is foundational** - Every query, every table, every S3 key must include tenant_id
2. **Never store what you can tokenize** - Payment data goes to Stripe, not your DB
3. **Encrypt three ways** - In transit (TLS), at rest (disk), field-level (PII)
4. **Audit everything** - Immutable logs for security investigations and compliance
5. **Policies in database** - Business rules should be configurable without code changes
6. **Secrets in vault** - Never in code, never in environment variables
7. **Assume breach** - Design for "when", not "if" - minimize blast radius
8. **Test DR regularly** - Untested backups are not backups

**Security is not a feature, it's the foundation.** 🔒
