CREATE EXTENSION IF NOT EXISTS vector;
--
-- PostgreSQL database dump
--


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
-- Name: approvals; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA approvals;


--
-- Name: checkpoints; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA checkpoints;


--
-- Name: memory_store; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA memory_store;


--
-- Name: rag; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA rag;


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: conversations_search_trigger(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.conversations_search_trigger() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    BEGIN
      NEW.search_vector :=
        setweight(to_tsvector('english', coalesce(NEW.summary, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(NEW.customer_name, '')), 'B') ||
        setweight(to_tsvector('english', coalesce(NEW.customer_identifier, '')), 'B');
      RETURN NEW;
    END;
    $$;


--
-- Name: update_conversation_search_vector(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_conversation_search_vector() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
          NEW.search_vector := 
            setweight(to_tsvector('english', coalesce(NEW.summary, '')), 'A') || 
            setweight(to_tsvector('english', coalesce(NEW.customer_name, '')), 'B') || 
            setweight(to_tsvector('english', coalesce(NEW.customer_identifier, '')), 'B');
          RETURN NEW;
        END
        $$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: executed_actions; Type: TABLE; Schema: approvals; Owner: -
--

CREATE TABLE approvals.executed_actions (
    idempotency_key text NOT NULL,
    session_id text NOT NULL,
    turn_id text NOT NULL,
    action_type text NOT NULL,
    payload jsonb NOT NULL,
    status text DEFAULT 'completed'::text NOT NULL,
    executed_at timestamp with time zone DEFAULT now()
);


--
-- Name: checkpoint_blobs; Type: TABLE; Schema: checkpoints; Owner: -
--

CREATE TABLE checkpoints.checkpoint_blobs (
    thread_id text NOT NULL,
    checkpoint_ns text DEFAULT ''::text NOT NULL,
    channel text NOT NULL,
    version text NOT NULL,
    type text NOT NULL,
    blob bytea
);


--
-- Name: checkpoint_migrations; Type: TABLE; Schema: checkpoints; Owner: -
--

CREATE TABLE checkpoints.checkpoint_migrations (
    v integer NOT NULL
);


--
-- Name: checkpoint_writes; Type: TABLE; Schema: checkpoints; Owner: -
--

CREATE TABLE checkpoints.checkpoint_writes (
    thread_id text NOT NULL,
    checkpoint_ns text DEFAULT ''::text NOT NULL,
    checkpoint_id text NOT NULL,
    task_id text NOT NULL,
    idx integer NOT NULL,
    channel text NOT NULL,
    type text,
    blob bytea NOT NULL,
    task_path text DEFAULT ''::text NOT NULL
);


--
-- Name: checkpoints; Type: TABLE; Schema: checkpoints; Owner: -
--

CREATE TABLE checkpoints.checkpoints (
    thread_id text NOT NULL,
    checkpoint_ns text DEFAULT ''::text NOT NULL,
    checkpoint_id text NOT NULL,
    parent_checkpoint_id text,
    type text,
    checkpoint jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: store; Type: TABLE; Schema: memory_store; Owner: -
--

CREATE TABLE memory_store.store (
    prefix text NOT NULL,
    key text NOT NULL,
    value jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamp with time zone,
    ttl_minutes integer
);


--
-- Name: store_migrations; Type: TABLE; Schema: memory_store; Owner: -
--

CREATE TABLE memory_store.store_migrations (
    v integer NOT NULL
);


--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: approval_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.approval_requests (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    agent_id character varying NOT NULL,
    action_type character varying NOT NULL,
    payload jsonb NOT NULL,
    risk_level character varying NOT NULL,
    reviewer_role character varying,
    status character varying NOT NULL,
    operator_note character varying,
    resolved_by_user_id uuid,
    expires_at timestamp with time zone,
    resolved_at timestamp with time zone,
    created_at timestamp with time zone
);


--
-- Name: conversation_turns; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.conversation_turns (
    id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    turn_index integer NOT NULL,
    role character varying NOT NULL,
    content character varying,
    agent_id character varying,
    latency_ms integer,
    input_tokens integer,
    output_tokens integer,
    created_at timestamp with time zone
);


--
-- Name: conversations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.conversations (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    customer_identifier character varying,
    status character varying NOT NULL,
    channel character varying NOT NULL,
    metadata jsonb,
    resolved_at timestamp with time zone,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    customer_name character varying,
    summary character varying,
    search_vector tsvector
);


--
-- Name: documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.documents (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    uploaded_by_user_id uuid NOT NULL,
    filename character varying NOT NULL,
    file_path character varying NOT NULL,
    file_type character varying NOT NULL,
    file_size_bytes integer NOT NULL,
    status character varying NOT NULL,
    error_message character varying,
    tags character varying[],
    chunk_count integer,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    CONSTRAINT chk_doc_file_size_positive CHECK ((file_size_bytes >= 0))
);


--
-- Name: user_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_sessions (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    refresh_token_hash character varying NOT NULL,
    user_agent character varying,
    ip_address character varying,
    expires_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid NOT NULL,
    email character varying NOT NULL,
    password_hash character varying NOT NULL,
    reset_password_token character varying,
    avatar_url character varying,
    deletion_scheduled_at timestamp with time zone,
    created_at timestamp with time zone,
    full_name character varying DEFAULT 'Unknown'::character varying NOT NULL,
    reset_password_expires_at timestamp with time zone,
    updated_at timestamp with time zone
);


--
-- Name: workspace_agent_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workspace_agent_config (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    active_provider character varying NOT NULL,
    mode character varying NOT NULL,
    global_model character varying,
    global_temperature double precision NOT NULL,
    global_system_prompt character varying,
    custom_models jsonb,
    custom_temperatures jsonb,
    custom_prompts jsonb,
    updated_at timestamp with time zone,
    custom_tools jsonb,
    custom_guardrails jsonb,
    custom_hitl_breakpoints jsonb
);


--
-- Name: workspace_integrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workspace_integrations (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    integration_type character varying NOT NULL,
    name character varying NOT NULL,
    config jsonb NOT NULL,
    status character varying NOT NULL,
    last_checked_at timestamp with time zone,
    created_at timestamp with time zone
);


--
-- Name: workspace_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workspace_members (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    user_id uuid NOT NULL,
    role character varying NOT NULL,
    created_at timestamp with time zone,
    invited_by_user_id uuid,
    status character varying DEFAULT 'active'::character varying NOT NULL
);


--
-- Name: workspace_notification_channels; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workspace_notification_channels (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    channel_type character varying NOT NULL,
    name character varying NOT NULL,
    config jsonb NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp with time zone
);


--
-- Name: workspace_notification_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workspace_notification_settings (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    event_type character varying NOT NULL,
    channel_id uuid NOT NULL,
    is_enabled boolean NOT NULL
);


--
-- Name: workspace_provider_keys; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workspace_provider_keys (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    provider character varying NOT NULL,
    encrypted_api_key character varying NOT NULL,
    key_hint character varying,
    is_verified boolean NOT NULL,
    created_at timestamp with time zone,
    updated_at timestamp with time zone
);


--
-- Name: workspaces; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workspaces (
    id uuid NOT NULL,
    name character varying NOT NULL,
    deletion_scheduled_at timestamp with time zone,
    created_at timestamp with time zone,
    plan character varying NOT NULL,
    stripe_customer_id character varying,
    updated_at timestamp with time zone
);


--
-- Name: document_chunks; Type: TABLE; Schema: rag; Owner: -
--

CREATE TABLE rag.document_chunks (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    chunk_index integer NOT NULL,
    content character varying NOT NULL,
    token_count integer,
    langchain_embedding_id uuid,
    created_at timestamp with time zone,
    CONSTRAINT chk_chunk_idx_positive CHECK ((chunk_index >= 0)),
    CONSTRAINT chk_token_count_positive CHECK ((token_count >= 0))
);


--
-- Name: langchain_pg_collection; Type: TABLE; Schema: rag; Owner: -
--

CREATE TABLE rag.langchain_pg_collection (
    uuid uuid NOT NULL,
    name character varying NOT NULL,
    cmetadata json
);


--
-- Name: langchain_pg_embedding; Type: TABLE; Schema: rag; Owner: -
--

CREATE TABLE rag.langchain_pg_embedding (
    id character varying NOT NULL,
    collection_id uuid,
    embedding public.vector,
    document character varying,
    cmetadata jsonb
);


--
-- Name: executed_actions executed_actions_pkey; Type: CONSTRAINT; Schema: approvals; Owner: -
--

ALTER TABLE ONLY approvals.executed_actions
    ADD CONSTRAINT executed_actions_pkey PRIMARY KEY (idempotency_key);


--
-- Name: checkpoint_blobs checkpoint_blobs_pkey; Type: CONSTRAINT; Schema: checkpoints; Owner: -
--

ALTER TABLE ONLY checkpoints.checkpoint_blobs
    ADD CONSTRAINT checkpoint_blobs_pkey PRIMARY KEY (thread_id, checkpoint_ns, channel, version);


--
-- Name: checkpoint_migrations checkpoint_migrations_pkey; Type: CONSTRAINT; Schema: checkpoints; Owner: -
--

ALTER TABLE ONLY checkpoints.checkpoint_migrations
    ADD CONSTRAINT checkpoint_migrations_pkey PRIMARY KEY (v);


--
-- Name: checkpoint_writes checkpoint_writes_pkey; Type: CONSTRAINT; Schema: checkpoints; Owner: -
--

ALTER TABLE ONLY checkpoints.checkpoint_writes
    ADD CONSTRAINT checkpoint_writes_pkey PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx);


--
-- Name: checkpoints checkpoints_pkey; Type: CONSTRAINT; Schema: checkpoints; Owner: -
--

ALTER TABLE ONLY checkpoints.checkpoints
    ADD CONSTRAINT checkpoints_pkey PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id);


--
-- Name: store_migrations store_migrations_pkey; Type: CONSTRAINT; Schema: memory_store; Owner: -
--

ALTER TABLE ONLY memory_store.store_migrations
    ADD CONSTRAINT store_migrations_pkey PRIMARY KEY (v);


--
-- Name: store store_pkey; Type: CONSTRAINT; Schema: memory_store; Owner: -
--

ALTER TABLE ONLY memory_store.store
    ADD CONSTRAINT store_pkey PRIMARY KEY (prefix, key);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: approval_requests approval_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_requests
    ADD CONSTRAINT approval_requests_pkey PRIMARY KEY (id);


--
-- Name: conversation_turns conversation_turns_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_turns
    ADD CONSTRAINT conversation_turns_pkey PRIMARY KEY (id);


--
-- Name: conversations conversations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_pkey PRIMARY KEY (id);


--
-- Name: documents documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_pkey PRIMARY KEY (id);


--
-- Name: conversation_turns uix_conversation_turn_index; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_turns
    ADD CONSTRAINT uix_conversation_turn_index UNIQUE (conversation_id, turn_index);


--
-- Name: workspace_notification_settings uix_workspace_event_channel; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_notification_settings
    ADD CONSTRAINT uix_workspace_event_channel UNIQUE (workspace_id, event_type, channel_id);


--
-- Name: workspace_provider_keys uix_workspace_provider; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_provider_keys
    ADD CONSTRAINT uix_workspace_provider UNIQUE (workspace_id, provider);


--
-- Name: workspace_members uix_workspace_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_members
    ADD CONSTRAINT uix_workspace_user UNIQUE (workspace_id, user_id);


--
-- Name: user_sessions user_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_sessions
    ADD CONSTRAINT user_sessions_pkey PRIMARY KEY (id);


--
-- Name: user_sessions user_sessions_refresh_token_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_sessions
    ADD CONSTRAINT user_sessions_refresh_token_hash_key UNIQUE (refresh_token_hash);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: workspace_agent_config workspace_agent_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_agent_config
    ADD CONSTRAINT workspace_agent_config_pkey PRIMARY KEY (id);


--
-- Name: workspace_agent_config workspace_agent_config_workspace_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_agent_config
    ADD CONSTRAINT workspace_agent_config_workspace_id_key UNIQUE (workspace_id);


--
-- Name: workspace_integrations workspace_integrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_integrations
    ADD CONSTRAINT workspace_integrations_pkey PRIMARY KEY (id);


--
-- Name: workspace_members workspace_members_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_members
    ADD CONSTRAINT workspace_members_pkey PRIMARY KEY (id);


--
-- Name: workspace_notification_channels workspace_notification_channels_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_notification_channels
    ADD CONSTRAINT workspace_notification_channels_pkey PRIMARY KEY (id);


--
-- Name: workspace_notification_settings workspace_notification_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_notification_settings
    ADD CONSTRAINT workspace_notification_settings_pkey PRIMARY KEY (id);


--
-- Name: workspace_provider_keys workspace_provider_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_provider_keys
    ADD CONSTRAINT workspace_provider_keys_pkey PRIMARY KEY (id);


--
-- Name: workspaces workspaces_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspaces
    ADD CONSTRAINT workspaces_pkey PRIMARY KEY (id);


--
-- Name: document_chunks document_chunks_pkey; Type: CONSTRAINT; Schema: rag; Owner: -
--

ALTER TABLE ONLY rag.document_chunks
    ADD CONSTRAINT document_chunks_pkey PRIMARY KEY (id);


--
-- Name: langchain_pg_collection langchain_pg_collection_name_key; Type: CONSTRAINT; Schema: rag; Owner: -
--

ALTER TABLE ONLY rag.langchain_pg_collection
    ADD CONSTRAINT langchain_pg_collection_name_key UNIQUE (name);


--
-- Name: langchain_pg_collection langchain_pg_collection_pkey; Type: CONSTRAINT; Schema: rag; Owner: -
--

ALTER TABLE ONLY rag.langchain_pg_collection
    ADD CONSTRAINT langchain_pg_collection_pkey PRIMARY KEY (uuid);


--
-- Name: langchain_pg_embedding langchain_pg_embedding_pkey; Type: CONSTRAINT; Schema: rag; Owner: -
--

ALTER TABLE ONLY rag.langchain_pg_embedding
    ADD CONSTRAINT langchain_pg_embedding_pkey PRIMARY KEY (id);


--
-- Name: idx_executed_actions_session; Type: INDEX; Schema: approvals; Owner: -
--

CREATE INDEX idx_executed_actions_session ON approvals.executed_actions USING btree (session_id);


--
-- Name: checkpoint_blobs_thread_id_idx; Type: INDEX; Schema: checkpoints; Owner: -
--

CREATE INDEX checkpoint_blobs_thread_id_idx ON checkpoints.checkpoint_blobs USING btree (thread_id);


--
-- Name: checkpoint_writes_thread_id_idx; Type: INDEX; Schema: checkpoints; Owner: -
--

CREATE INDEX checkpoint_writes_thread_id_idx ON checkpoints.checkpoint_writes USING btree (thread_id);


--
-- Name: checkpoints_thread_id_idx; Type: INDEX; Schema: checkpoints; Owner: -
--

CREATE INDEX checkpoints_thread_id_idx ON checkpoints.checkpoints USING btree (thread_id);


--
-- Name: idx_store_expires_at; Type: INDEX; Schema: memory_store; Owner: -
--

CREATE INDEX idx_store_expires_at ON memory_store.store USING btree (expires_at) WHERE (expires_at IS NOT NULL);


--
-- Name: store_prefix_idx; Type: INDEX; Schema: memory_store; Owner: -
--

CREATE INDEX store_prefix_idx ON memory_store.store USING btree (prefix text_pattern_ops);


--
-- Name: ix_approval_requests_conversation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_requests_conversation_id ON public.approval_requests USING btree (conversation_id);


--
-- Name: ix_approvals_workspace_id_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approvals_workspace_id_created_at ON public.approval_requests USING btree (workspace_id, created_at);


--
-- Name: ix_approvals_workspace_id_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approvals_workspace_id_status ON public.approval_requests USING btree (workspace_id, status);


--
-- Name: ix_conversation_turns_conversation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_conversation_turns_conversation_id ON public.conversation_turns USING btree (conversation_id);


--
-- Name: ix_conversation_turns_workspace_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_conversation_turns_workspace_created_at ON public.conversation_turns USING btree (workspace_id, created_at);


--
-- Name: ix_conversations_search_vector; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_conversations_search_vector ON public.conversations USING gin (search_vector);


--
-- Name: ix_conversations_workspace_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_conversations_workspace_id ON public.conversations USING btree (workspace_id);


--
-- Name: ix_conversations_workspace_id_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_conversations_workspace_id_created_at ON public.conversations USING btree (workspace_id, created_at);


--
-- Name: ix_conversations_workspace_id_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_conversations_workspace_id_status ON public.conversations USING btree (workspace_id, status);


--
-- Name: ix_documents_workspace_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_documents_workspace_id ON public.documents USING btree (workspace_id);


--
-- Name: ix_documents_workspace_id_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_documents_workspace_id_status ON public.documents USING btree (workspace_id, status);


--
-- Name: ix_user_sessions_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_sessions_expires_at ON public.user_sessions USING btree (expires_at);


--
-- Name: ix_user_sessions_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_sessions_user_id ON public.user_sessions USING btree (user_id);


--
-- Name: ix_users_deletion_scheduled_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_deletion_scheduled_at ON public.users USING btree (deletion_scheduled_at);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: ix_workspace_members_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workspace_members_user_id ON public.workspace_members USING btree (user_id);


--
-- Name: ix_workspace_members_workspace_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workspace_members_workspace_id ON public.workspace_members USING btree (workspace_id);


--
-- Name: ix_workspace_notification_channels_workspace_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workspace_notification_channels_workspace_id ON public.workspace_notification_channels USING btree (workspace_id);


--
-- Name: ix_workspaces_deletion_scheduled_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workspaces_deletion_scheduled_at ON public.workspaces USING btree (deletion_scheduled_at);


--
-- Name: ix_cmetadata_gin; Type: INDEX; Schema: rag; Owner: -
--

CREATE INDEX ix_cmetadata_gin ON rag.langchain_pg_embedding USING gin (cmetadata jsonb_path_ops);


--
-- Name: ix_rag_document_chunks_document_id; Type: INDEX; Schema: rag; Owner: -
--

CREATE INDEX ix_rag_document_chunks_document_id ON rag.document_chunks USING btree (document_id);


--
-- Name: ix_rag_document_chunks_workspace_id; Type: INDEX; Schema: rag; Owner: -
--

CREATE INDEX ix_rag_document_chunks_workspace_id ON rag.document_chunks USING btree (workspace_id);


--
-- Name: conversations conversations_search_update; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER conversations_search_update BEFORE INSERT OR UPDATE ON public.conversations FOR EACH ROW EXECUTE FUNCTION public.conversations_search_trigger();


--
-- Name: conversations trg_conversation_search_vector; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_conversation_search_vector BEFORE INSERT OR UPDATE OF summary, customer_name, customer_identifier ON public.conversations FOR EACH ROW EXECUTE FUNCTION public.update_conversation_search_vector();


--
-- Name: approval_requests approval_requests_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_requests
    ADD CONSTRAINT approval_requests_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: approval_requests approval_requests_resolved_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_requests
    ADD CONSTRAINT approval_requests_resolved_by_user_id_fkey FOREIGN KEY (resolved_by_user_id) REFERENCES public.users(id);


--
-- Name: approval_requests approval_requests_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_requests
    ADD CONSTRAINT approval_requests_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: conversation_turns conversation_turns_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_turns
    ADD CONSTRAINT conversation_turns_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: conversations conversations_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: documents documents_uploaded_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_uploaded_by_user_id_fkey FOREIGN KEY (uploaded_by_user_id) REFERENCES public.users(id);


--
-- Name: documents documents_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: user_sessions user_sessions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_sessions
    ADD CONSTRAINT user_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: workspace_agent_config workspace_agent_config_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_agent_config
    ADD CONSTRAINT workspace_agent_config_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: workspace_integrations workspace_integrations_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_integrations
    ADD CONSTRAINT workspace_integrations_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: workspace_members workspace_members_invited_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_members
    ADD CONSTRAINT workspace_members_invited_by_user_id_fkey FOREIGN KEY (invited_by_user_id) REFERENCES public.users(id);


--
-- Name: workspace_members workspace_members_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_members
    ADD CONSTRAINT workspace_members_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: workspace_members workspace_members_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_members
    ADD CONSTRAINT workspace_members_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: workspace_notification_channels workspace_notification_channels_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_notification_channels
    ADD CONSTRAINT workspace_notification_channels_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: workspace_notification_settings workspace_notification_settings_channel_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_notification_settings
    ADD CONSTRAINT workspace_notification_settings_channel_id_fkey FOREIGN KEY (channel_id) REFERENCES public.workspace_notification_channels(id) ON DELETE CASCADE;


--
-- Name: workspace_notification_settings workspace_notification_settings_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_notification_settings
    ADD CONSTRAINT workspace_notification_settings_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: workspace_provider_keys workspace_provider_keys_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_provider_keys
    ADD CONSTRAINT workspace_provider_keys_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: document_chunks document_chunks_document_id_fkey; Type: FK CONSTRAINT; Schema: rag; Owner: -
--

ALTER TABLE ONLY rag.document_chunks
    ADD CONSTRAINT document_chunks_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: langchain_pg_embedding langchain_pg_embedding_collection_id_fkey; Type: FK CONSTRAINT; Schema: rag; Owner: -
--

ALTER TABLE ONLY rag.langchain_pg_embedding
    ADD CONSTRAINT langchain_pg_embedding_collection_id_fkey FOREIGN KEY (collection_id) REFERENCES rag.langchain_pg_collection(uuid) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict laJgORs0ky3NXUYRrIDz5ounLQMt6XgxNEdthT0X3XW7XXNMNaNOZUwUPzwkIeW

