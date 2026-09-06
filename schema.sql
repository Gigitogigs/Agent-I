--
-- PostgreSQL database dump
--

\restrict 5uuwRZooFGO7nk5lIDXqBR8OUVGP53oTS3HcbYpcCMBicubaGt1SyR8TPdLRRXf

-- Dumped from database version 18.4
-- Dumped by pg_dump version 18.4

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: approvals; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA approvals;


ALTER SCHEMA approvals OWNER TO postgres;

--
-- Name: checkpoints; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA checkpoints;


ALTER SCHEMA checkpoints OWNER TO postgres;

--
-- Name: memory_store; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA memory_store;


ALTER SCHEMA memory_store OWNER TO postgres;

--
-- Name: rag; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA rag;


ALTER SCHEMA rag OWNER TO postgres;

--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: approval_requests; Type: TABLE; Schema: approvals; Owner: postgres
--

CREATE TABLE approvals.approval_requests (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    session_id text NOT NULL,
    agent_id text NOT NULL,
    action_type text NOT NULL,
    payload jsonb NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    reviewer_role text,
    risk_level text DEFAULT 'medium'::text NOT NULL,
    expires_at timestamp with time zone,
    resolved_at timestamp with time zone,
    resolved_by text,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT approval_requests_risk_level_check CHECK ((risk_level = ANY (ARRAY['low'::text, 'medium'::text, 'high'::text, 'critical'::text]))),
    CONSTRAINT approval_requests_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'approved'::text, 'rejected'::text, 'expired'::text, 'cancelled'::text])))
);


ALTER TABLE approvals.approval_requests OWNER TO postgres;

--
-- Name: langchain_pg_collection; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.langchain_pg_collection (
    uuid uuid NOT NULL,
    name character varying NOT NULL,
    cmetadata json
);


ALTER TABLE public.langchain_pg_collection OWNER TO postgres;

--
-- Name: langchain_pg_embedding; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.langchain_pg_embedding (
    id character varying NOT NULL,
    collection_id uuid,
    embedding public.vector,
    document character varying,
    cmetadata jsonb
);


ALTER TABLE public.langchain_pg_embedding OWNER TO postgres;

--
-- Name: documents; Type: TABLE; Schema: rag; Owner: postgres
--

CREATE TABLE rag.documents (
    id bigint NOT NULL,
    doc_id text NOT NULL,
    title text,
    content text NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb,
    embedding public.vector(1024),
    fts tsvector GENERATED ALWAYS AS (to_tsvector('english'::regconfig, content)) STORED,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE rag.documents OWNER TO postgres;

--
-- Name: documents_id_seq; Type: SEQUENCE; Schema: rag; Owner: postgres
--

CREATE SEQUENCE rag.documents_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE rag.documents_id_seq OWNER TO postgres;

--
-- Name: documents_id_seq; Type: SEQUENCE OWNED BY; Schema: rag; Owner: postgres
--

ALTER SEQUENCE rag.documents_id_seq OWNED BY rag.documents.id;


--
-- Name: resolved_tickets; Type: TABLE; Schema: rag; Owner: postgres
--

CREATE TABLE rag.resolved_tickets (
    id bigint NOT NULL,
    ticket_id text NOT NULL,
    summary text NOT NULL,
    resolution text NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb,
    embedding public.vector(1024),
    fts tsvector GENERATED ALWAYS AS (to_tsvector('english'::regconfig, ((summary || ' '::text) || resolution))) STORED,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE rag.resolved_tickets OWNER TO postgres;

--
-- Name: resolved_tickets_id_seq; Type: SEQUENCE; Schema: rag; Owner: postgres
--

CREATE SEQUENCE rag.resolved_tickets_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE rag.resolved_tickets_id_seq OWNER TO postgres;

--
-- Name: resolved_tickets_id_seq; Type: SEQUENCE OWNED BY; Schema: rag; Owner: postgres
--

ALTER SEQUENCE rag.resolved_tickets_id_seq OWNED BY rag.resolved_tickets.id;


--
-- Name: documents id; Type: DEFAULT; Schema: rag; Owner: postgres
--

ALTER TABLE ONLY rag.documents ALTER COLUMN id SET DEFAULT nextval('rag.documents_id_seq'::regclass);


--
-- Name: resolved_tickets id; Type: DEFAULT; Schema: rag; Owner: postgres
--

ALTER TABLE ONLY rag.resolved_tickets ALTER COLUMN id SET DEFAULT nextval('rag.resolved_tickets_id_seq'::regclass);


--
-- Name: approval_requests approval_requests_pkey; Type: CONSTRAINT; Schema: approvals; Owner: postgres
--

ALTER TABLE ONLY approvals.approval_requests
    ADD CONSTRAINT approval_requests_pkey PRIMARY KEY (id);


--
-- Name: langchain_pg_collection langchain_pg_collection_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.langchain_pg_collection
    ADD CONSTRAINT langchain_pg_collection_name_key UNIQUE (name);


--
-- Name: langchain_pg_collection langchain_pg_collection_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.langchain_pg_collection
    ADD CONSTRAINT langchain_pg_collection_pkey PRIMARY KEY (uuid);


--
-- Name: langchain_pg_embedding langchain_pg_embedding_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.langchain_pg_embedding
    ADD CONSTRAINT langchain_pg_embedding_pkey PRIMARY KEY (id);


--
-- Name: documents documents_doc_id_key; Type: CONSTRAINT; Schema: rag; Owner: postgres
--

ALTER TABLE ONLY rag.documents
    ADD CONSTRAINT documents_doc_id_key UNIQUE (doc_id);


--
-- Name: documents documents_pkey; Type: CONSTRAINT; Schema: rag; Owner: postgres
--

ALTER TABLE ONLY rag.documents
    ADD CONSTRAINT documents_pkey PRIMARY KEY (id);


--
-- Name: resolved_tickets resolved_tickets_pkey; Type: CONSTRAINT; Schema: rag; Owner: postgres
--

ALTER TABLE ONLY rag.resolved_tickets
    ADD CONSTRAINT resolved_tickets_pkey PRIMARY KEY (id);


--
-- Name: resolved_tickets resolved_tickets_ticket_id_key; Type: CONSTRAINT; Schema: rag; Owner: postgres
--

ALTER TABLE ONLY rag.resolved_tickets
    ADD CONSTRAINT resolved_tickets_ticket_id_key UNIQUE (ticket_id);


--
-- Name: ix_cmetadata_gin; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_cmetadata_gin ON public.langchain_pg_embedding USING gin (cmetadata jsonb_path_ops);


--
-- Name: documents_embedding_hnsw; Type: INDEX; Schema: rag; Owner: postgres
--

CREATE INDEX documents_embedding_hnsw ON rag.documents USING hnsw (embedding public.vector_cosine_ops) WITH (m='16', ef_construction='64');


--
-- Name: documents_fts_idx; Type: INDEX; Schema: rag; Owner: postgres
--

CREATE INDEX documents_fts_idx ON rag.documents USING gin (fts);


--
-- Name: documents_metadata_idx; Type: INDEX; Schema: rag; Owner: postgres
--

CREATE INDEX documents_metadata_idx ON rag.documents USING gin (metadata);


--
-- Name: resolved_tickets_embedding_hnsw; Type: INDEX; Schema: rag; Owner: postgres
--

CREATE INDEX resolved_tickets_embedding_hnsw ON rag.resolved_tickets USING hnsw (embedding public.vector_cosine_ops) WITH (m='16', ef_construction='64');


--
-- Name: resolved_tickets_fts_idx; Type: INDEX; Schema: rag; Owner: postgres
--

CREATE INDEX resolved_tickets_fts_idx ON rag.resolved_tickets USING gin (fts);


--
-- Name: langchain_pg_embedding langchain_pg_embedding_collection_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.langchain_pg_embedding
    ADD CONSTRAINT langchain_pg_embedding_collection_id_fkey FOREIGN KEY (collection_id) REFERENCES public.langchain_pg_collection(uuid) ON DELETE CASCADE;


--
-- Name: approval_requests agent_isolation; Type: POLICY; Schema: approvals; Owner: postgres
--

CREATE POLICY agent_isolation ON approvals.approval_requests USING ((session_id = current_setting('app.current_session_id'::text, true)));


--
-- Name: approval_requests; Type: ROW SECURITY; Schema: approvals; Owner: postgres
--

ALTER TABLE approvals.approval_requests ENABLE ROW LEVEL SECURITY;

--
-- PostgreSQL database dump complete
--

\unrestrict 5uuwRZooFGO7nk5lIDXqBR8OUVGP53oTS3HcbYpcCMBicubaGt1SyR8TPdLRRXf

