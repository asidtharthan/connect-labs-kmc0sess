"""
KMC Image Audit — cross-LLO scale-photo audit with per-opportunity AI routing.

Why this template exists
------------------------
KMC's existing options each fall short in a specific way:

* ``bulk_image_audit`` (wf 5113) works, but its AI agent list is hardcoded, it has no
  sampling controls, and one agent applies to the whole run — which is wrong for KMC
  because scale hardware differs by LLO.
* ``weekly_dual_track_audit`` has the better operating model (census one image type,
  sample the rest, run on a schedule) but its template lives outside this repo and its
  classifier registry has no analog-dial entry, so it cannot serve EHA/BERI/NAMA.

The deciding constraint is hardware: PIPN uses digital scales, EHA/BERI/NAMA use analog
dials, and *within program 46 both appear side by side*. So the agent has to be chosen
per opportunity, not per run. That is this template's core idea, and the reason it fans
out one single-opportunity audit per selected opp rather than one audit for all of them.

Design notes worth knowing before editing
-----------------------------------------
* **Per-opp fan-out is deliberate.** Setting ``opportunity_ids`` and relying on the
  backend's multi-opp routing produced zero sessions for every non-home opportunity when
  it was tried on wf 5113. Firing one single-opp ``createAudit`` per opportunity — the
  pattern the KMC dashboard already uses in production — works. Keep it.
* **Sessions are stored scoped per opportunity**, so the results fetch loops the opp set
  and merges. Fetching ``/sessions/`` without ``?opportunity_id=`` only ever returns the
  home opp's sessions, which reads as "0 sessions" for everything else.
* **Image extraction differs between this repo and the deployed backend.** The copy of
  ``_filter_visits_by_related_fields`` in this repo filters *visits* and returns every image
  on a matched visit — running it locally against opp 1487 produced four question types and
  161 of 308 images (52%) with no reading. The DEPLOYED backend also narrows to the
  requested image path: live run 13250 extracted 858 images across 6 opportunities, all of
  them ``anthropometric/upload_weight_image`` and all 858 carrying a reading. The repo is
  behind. The "images without a reading" warning is kept as a guard — it simply does not
  fire on the deployed path — and must not be removed on the assumption that it is dead.
* **There is no per-image-type sampling and no FLW cap.** ``AuditCriteria`` accepts only
  ``sample_percentage`` for a date-range audit (``count_per_flw`` applies solely to
  ``last_n_per_flw``, and ``max_flws`` does not exist — passing it is silently ignored).
  An earlier draft of this template exposed both; they were removed rather than shipped
  as controls that quietly do nothing.
"""

# Scale hardware per LLO drives which AI agent scores the photo. Sources: per-project
# procurement (EHA/BERI Salter 235 dials, NAMA KINLee dials, PIPN digital); GHI-KE and
# Kikapu are UNCONFIRMED and provisionally treated as digital — the UI flags them as
# unverified so nobody reads a green verdict there as settled.
DIGITAL = "digital"
DIAL = "dial"

OPP_META = {
    523: {"llo": "NAMA", "country": "Uganda", "version": "V0/V1", "scale": DIAL, "program": 46},
    524: {"llo": "PIPN", "country": "Uganda", "version": "V0/V1", "scale": DIGITAL, "program": 46},
    675: {
        "llo": "GHI-KE",
        "country": "Kenya",
        "version": "V0/V1",
        "scale": DIGITAL,
        "program": 68,
        "unverified": True,
    },
    874: {"llo": "PIPN", "country": "Uganda", "version": "V2", "scale": DIGITAL, "program": 46},
    938: {"llo": "NAMA", "country": "Uganda", "version": "V2", "scale": DIAL, "program": 46},
    1234: {"llo": "GHI-KE", "country": "Kenya", "version": "V2", "scale": DIGITAL, "program": 68, "unverified": True},
    1236: {"llo": "EHA", "country": "Nigeria", "version": "V2+", "scale": DIAL, "program": 114},
    1487: {"llo": "PIPN", "country": "Uganda", "version": "V3", "scale": DIGITAL, "program": 46},
    1488: {"llo": "NAMA", "country": "Uganda", "version": "V3", "scale": DIAL, "program": 46},
    1739: {"llo": "Kikapu", "country": "Kenya", "version": "V3", "scale": DIGITAL, "program": 68, "unverified": True},
    1790: {"llo": "BERI", "country": "Nigeria", "version": "V3", "scale": DIAL, "program": 114},
}

# The follow-up weight photo and the typed reading it is checked against. Verified against
# raw form JSON for all 11 opportunities. Registration photos live at
# child_details/upload_weight_image instead and are NOT audited here — that path carries
# ~29% of all KMC weight images and is a deliberate, flagged omission, not an oversight.
WEIGHT_IMAGE_PATH = "anthropometric/upload_weight_image"
WEIGHT_FIELD_PATH = "child_weight_visit"

AGENT_FOR_SCALE = {DIGITAL: "scale_validation", DIAL: "scale_dial_read"}

DEFINITION = {
    "name": "KMC Image Audit",
    "description": (
        "Scale-photo audit across KMC's LLOs with the AI agent chosen per opportunity by scale "
        "hardware — digital LLOs scored by Scale [Digital], analog-dial LLOs by Scale [Dial]. "
        "Audits the follow-up weight photo against the typed reading, per FLW, across every "
        "selected opportunity in one run."
    ),
    "version": 1,
    "templateType": "kmc_image_audit",
    "statuses": [
        {"id": "config", "label": "Configuring", "color": "gray"},
        {"id": "creating", "label": "Creating Audits", "color": "blue"},
        {"id": "created", "label": "Audits Created", "color": "green"},
        {"id": "failed", "label": "Failed", "color": "red"},
    ],
    "config": {
        "multi_opp": True,
        "showSummaryCards": True,
        "opp_meta": OPP_META,
        "weight_image_path": WEIGHT_IMAGE_PATH,
        "weight_field_path": WEIGHT_FIELD_PATH,
        "agent_for_scale": AGENT_FOR_SCALE,
    },
    "pipeline_sources": [],
}

RENDER_CODE = """function WorkflowUI({ definition, instance, actions, onUpdateState, view }) {
    // ── Pinned config ─────────────────────────────────────────────────────────
    const cfg = definition.config || {};
    const OPP_META = cfg.opp_meta || {};
    const WEIGHT_IMAGE_PATH = cfg.weight_image_path || 'anthropometric/upload_weight_image';
    const WEIGHT_FIELD_PATH = cfg.weight_field_path || 'child_weight_visit';
    const AGENT_FOR_SCALE = cfg.agent_for_scale || { digital: 'scale_validation', dial: 'scale_dial_read' };

    const allOppIds = Object.keys(OPP_META).map(s => parseInt(s, 10)).sort((a, b) => a - b);
    const meta = (id) => OPP_META[String(id)] || {};
    const oppLabel = (id) => {
        const m = meta(id);
        return m.llo ? (m.llo + ' ' + (m.version || '') + ' · ' + (m.country || '')) : ('Opportunity ' + id);
    };
    const scaleOf = (id) => meta(id).scale || 'digital';
    const agentFor = (id) => AGENT_FOR_SCALE[scaleOf(id)] || 'scale_validation';

    // ── Selection + window ────────────────────────────────────────────────────
    const runState = (view && view.state) || instance.state || {};
    const [selected, setSelected] = React.useState(runState.selected_opps || []);
    const [datePreset, setDatePreset] = React.useState(runState.date_preset || 'last_week');
    const [startDate, setStartDate] = React.useState(runState.window_start || '');
    const [endDate, setEndDate] = React.useState(runState.window_end || '');
    // Volume control. sample_percentage is the ONLY lever this backend honours for a
    // date_range audit: count_per_flw applies solely to last_n_per_flw, and there is no
    // max_flws in AuditCriteria at all (passing one is silently ignored). Sampling is per
    // FLW, so every worker keeps representation rather than the busiest ones crowding out
    // the rest -- see filter_visits_for_audit.
    const [samplePct, setSamplePct] = React.useState(runState.sample_percentage != null ? runState.sample_percentage : 100);
    // Per-opp agent override. Defaults come from scale hardware; an override is kept per
    // opportunity so a mixed-hardware program (46 has both) stays correct.
    const [agentOverride, setAgentOverride] = React.useState(runState.agent_override || {});
    const effectiveAgent = (id) => agentOverride[String(id)] || agentFor(id);

    const calcRange = (preset) => {
        const today = new Date(); today.setHours(0, 0, 0, 0);
        let start, end;
        if (preset === 'last_week') {
            const dow = today.getDay();
            const thisSun = new Date(today); thisSun.setDate(today.getDate() - dow);
            end = new Date(thisSun); end.setDate(thisSun.getDate() - 1);
            start = new Date(thisSun); start.setDate(thisSun.getDate() - 7);
        } else if (preset === 'last_7_days' || preset === 'last_14_days' || preset === 'last_30_days') {
            const n = preset === 'last_7_days' ? 7 : (preset === 'last_14_days' ? 14 : 30);
            end = new Date(today); end.setDate(today.getDate() - 1);
            start = new Date(end); start.setDate(end.getDate() - (n - 1));
        } else { return null; }
        const iso = (d) => d.toISOString().split('T')[0];
        return { start: iso(start), end: iso(end) };
    };
    const applyPreset = (p) => {
        setDatePreset(p);
        if (p !== 'custom') { const r = calcRange(p); if (r) { setStartDate(r.start); setEndDate(r.end); } }
    };
    React.useEffect(() => { if (!startDate && !endDate) applyPreset('last_week'); }, []);

    // ── Agent registry (live, so a newly deployed agent appears without a code change) ──
    const [agents, setAgents] = React.useState([]);
    const [agentsError, setAgentsError] = React.useState(null);
    React.useEffect(() => {
        fetch('/audit/api/ai-agents/')
            .then(r => r.json())
            .then(d => setAgents((d && d.agents) || []))
            .catch(e => setAgentsError(String(e && e.message ? e.message : e)));
    }, []);
    const agentName = (id) => {
        const a = agents.find(x => x.agent_id === id);
        return a ? a.name : id;
    };
    const agentKnown = (id) => !agents.length || agents.some(x => x.agent_id === id);

    // ── Sessions, merged across every opportunity in the run ───────────────────
    // Sessions are stored scoped per opportunity, so a single unscoped fetch returns only
    // the home opp's — which is exactly how a working run comes to report "0 sessions".
    const [sessions, setSessions] = React.useState([]);
    const [loadingSessions, setLoadingSessions] = React.useState(true);
    const refreshSessions = () => {
        const ids = (selected.length ? selected : allOppIds);
        if (!instance.id || !ids.length) { setLoadingSessions(false); return Promise.resolve([]); }
        return Promise.all(ids.map(oid =>
            fetch('/audit/api/workflow/' + instance.id + '/sessions/?opportunity_id=' + oid)
                .then(r => r.json())
                .then(d => ((d && d.success && d.sessions) ? d.sessions.map(s => Object.assign({ _opp: oid }, s)) : []))
                .catch(() => [])
        )).then(arrs => {
            const seen = {}; const all = [];
            arrs.forEach(list => list.forEach(s => { if (!seen[s.id]) { seen[s.id] = true; all.push(s); } }));
            setSessions(all); setLoadingSessions(false); return all;
        }).catch(() => { setLoadingSessions(false); return []; });
    };
    React.useEffect(() => { refreshSessions(); }, [instance.id]);

    // ── Run execution ─────────────────────────────────────────────────────────
    const [isRunning, setIsRunning] = React.useState(false);
    const [progress, setProgress] = React.useState(null);
    const [runError, setRunError] = React.useState(null);
    const cleanupsRef = React.useRef([]);
    React.useEffect(() => () => { cleanupsRef.current.forEach(c => { try { if (c) c(); } catch (e) {} }); }, []);

    // Poll while a run is in flight so the live panel shows OUR counts. The server's progress
    // string reports "(N passed, M failed)" and omits errors entirely — on run 13575 it read
    // "110/140 images (1 passed, 0 failed)" while 109 of those 110 had errored. Read literally,
    // that line says a healthy run is in progress.
    React.useEffect(() => {
        if (!isRunning) return undefined;
        const t = setInterval(() => { refreshSessions(); }, 20000);
        return () => clearInterval(t);
    }, [isRunning]);

    const toggleOpp = (id) => setSelected(prev =>
        prev.indexOf(id) >= 0 ? prev.filter(x => x !== id) : prev.concat([id]).sort((a, b) => a - b));
    const selectAll = () => setSelected(allOppIds.slice());
    const selectNone = () => setSelected([]);
    const selectScale = (kind) => setSelected(allOppIds.filter(id => scaleOf(id) === kind));

    const buildCriteria = (oppId) => {
        // filter_by_image narrows VISIT selection to visits carrying the weight photo, so we
        // do not pull visits with no photo at all. It does not narrow the images themselves:
        // every image on a matched visit is extracted, which is why the summary reports how
        // many arrived without a reading rather than pretending the run is weight-only.
        const relatedFields = [{
            image_path: WEIGHT_IMAGE_PATH,
            field_path: WEIGHT_FIELD_PATH,
            label: 'Scale Weight Reading',
            filter_by_image: true,
        }];
        return {
            audit_type: 'date_range',
            granularity: 'per_flw',
            start_date: startDate,
            end_date: endDate,
            sample_percentage: Number(samplePct) > 0 ? Number(samplePct) : 100,
            related_fields: relatedFields,
            title: 'KMC Image Audit · ' + oppLabel(oppId) + ' · ' + startDate + ' → ' + endDate,
            // Stamped onto every session the backend creates, so these are findable later
            // without inferring intent from the title string.
            tag: 'kmc_weight_photo',
        };
    };

    const handleCreate = async () => {
        if (!selected.length || !startDate || !endDate || isRunning) return;
        setIsRunning(true); setRunError(null);
        setProgress({ status: 'starting', message: 'Submitting ' + selected.length + ' audit(s)…' });

        await onUpdateState({
            selected_opps: selected, window_start: startDate, window_end: endDate,
            date_preset: datePreset, sample_percentage: Number(samplePct),
            agent_override: agentOverride,
        });

        let done = 0, failed = 0;
        const total = selected.length;
        const cleanups = [];
        const onOne = async () => {
            done += 1;
            setProgress({ status: 'running', message: 'Finished ' + done + ' of ' + total + ' opportunities', processed: done, total: total });
            if (done >= total) {
                await refreshSessions();
                setIsRunning(false);
                setProgress({ status: 'completed', message: 'Created audits for ' + (total - failed) + ' of ' + total + ' opportunities' });
            }
        };

        try {
            for (let k = 0; k < selected.length; k++) {
                const oid = selected[k];
                // One single-opportunity audit per opp. Multi-opp routing is deliberately
                // not used — it produced zero sessions for non-home opportunities.
                const res = await actions.createAudit({
                    opportunities: [{ id: oid, name: oppLabel(oid) }],
                    criteria: buildCriteria(oid),
                    workflow_run_id: instance.id,
                    ai_agent_id: effectiveAgent(oid),
                });
                if (!(res && res.success && res.task_id)) { failed += 1; await onOne(); continue; }
                setProgress({ status: 'running', message: 'Auditing ' + oppLabel(oid) + ' (' + (k + 1) + ' of ' + total + ')…', processed: done, total: total });

                // Wait for THIS opportunity before starting the next. Queuing them all at once
                // multiplies into (audits × ~10 images in flight) concurrent classifier calls,
                // and the scale models collapse above ~20: platform-side measurement put 5
                // parallel audits at 77 usable classifications/hour against 644 for one at a
                // time. Past the gateway's capacity every extra parallel audit is negative work
                // — it holds a 60s slot and returns nothing. Our own runs agree: three audits
                // fired within six minutes on 13 Aug failed 92–98%, while the same workflow run
                // one opportunity at a time on 14 Aug failed 0–20%.
                await new Promise((resolve) => {
                    let settled = false;
                    const finish = () => { if (!settled) { settled = true; resolve(); } };
                    // Safety net: if the progress stream drops we would otherwise wait forever
                    // and never start the remaining opportunities.
                    const guard = setTimeout(finish, 45 * 60 * 1000);
                    const cleanup = actions.streamAuditProgress(
                        res.task_id,
                        (p) => setProgress({
                            status: 'running',
                            message: (p && p.message) || ('Auditing ' + oppLabel(oid)),
                            processed: done, total: total,
                        }),
                        async () => { clearTimeout(guard); await onOne(); finish(); },
                        async () => { clearTimeout(guard); failed += 1; await onOne(); finish(); }
                    );
                    cleanups.push(cleanup);
                });
            }
            cleanupsRef.current = cleanups;
        } catch (err) {
            setIsRunning(false);
            setRunError(String(err && err.message ? err.message : err));
            setProgress({ status: 'failed', error: String(err && err.message ? err.message : err) });
        }
    };

    // ── Roll the session records up for display ───────────────────────────────
    // IMPORTANT: /audit/api/workflow/<id>/sessions/ returns to_summary_dict() — id, title, status,
    // opportunity_id, flw_username/flw_display_name, visit_count and assessment_stats. It does NOT
    // return visit_images or visit_results. An earlier version of this rollup walked those two and
    // consequently rendered 0 for every metric except the FLW count, on a run that had 858 images
    // and 845 verdicts sitting in the records. Read assessment_stats; do not reach for the raw
    // session data here.
    //
    // Substitutions, both verified against live run 13250:
    //   visit_count == image count            858 == 858 (this audit takes one weight photo per visit)
    //   visit_count - assessment_stats.total  == the images the AI never reached (13, exact)
    const rollup = React.useMemo(() => {
        const byOpp = {}; const byLlo = {};
        const T = { flws: 0, images: 0, assessed: 0, match: 0, noMatch: 0, error: 0, aiPending: 0,
            humanPass: 0, humanFail: 0, humanPending: 0, notReviewed: 0, unstarted: 0 };
        sessions.forEach(s => {
            const oid = s._opp || s.opportunity_id;
            const m = meta(oid);
            const o = byOpp[oid] || (byOpp[oid] = { opp: oid, llo: m.llo || '?', scale: m.scale || '?',
                sessions: 0, images: 0, assessed: 0, match: 0, noMatch: 0, error: 0, aiPending: 0,
                humanPass: 0, humanFail: 0, humanPending: 0, notReviewed: 0, unstarted: 0 });
            const st = s.assessment_stats || {};
            const imgs = s.visit_count || 0;
            const assessed = st.total || 0;
            const gap = Math.max(0, imgs - assessed);
            o.sessions += 1; T.flws += 1;
            o.images += imgs; T.images += imgs;
            o.assessed += assessed; T.assessed += assessed;
            o.match += st.ai_match || 0; T.match += st.ai_match || 0;
            o.noMatch += st.ai_no_match || 0; T.noMatch += st.ai_no_match || 0;
            o.error += st.ai_error || 0; T.error += st.ai_error || 0;
            o.aiPending += st.ai_pending || 0; T.aiPending += st.ai_pending || 0;
            o.humanPass += st.pass || 0; T.humanPass += st.pass || 0;
            o.humanFail += st.fail || 0; T.humanFail += st.fail || 0;
            o.humanPending += st.pending || 0; T.humanPending += st.pending || 0;
            o.notReviewed += gap; T.notReviewed += gap;
            if (imgs > 0 && assessed === 0) { o.unstarted += 1; T.unstarted += 1; }
        });
        Object.keys(byOpp).forEach(k => {
            const o = byOpp[k];
            const l = byLlo[o.llo] || (byLlo[o.llo] = { llo: o.llo, scale: o.scale, opps: 0, sessions: 0,
                images: 0, assessed: 0, match: 0, noMatch: 0, error: 0, notReviewed: 0, unstarted: 0 });
            l.opps += 1; l.sessions += o.sessions; l.images += o.images; l.assessed += o.assessed;
            l.match += o.match; l.noMatch += o.noMatch; l.error += o.error;
            l.notReviewed += o.notReviewed; l.unstarted += o.unstarted;
        });
        const scored = T.match + T.noMatch;
        const attempts = scored + T.error;
        return Object.assign({}, T, {
            byOpp: Object.keys(byOpp).map(k => byOpp[k]).sort((a, b) => a.llo.localeCompare(b.llo) || a.opp - b.opp),
            byLlo: Object.keys(byLlo).map(k => byLlo[k]).sort((a, b) => a.llo.localeCompare(b.llo)),
            scored: scored, reviewed: attempts,
            errorPct: attempts > 0 ? Math.round(100 * T.error / attempts) : 0,
            noMatchPct: scored > 0 ? Math.round(100 * T.noMatch / scored) : 0,
        });
    }, [sessions]);

    // ── Warnings: things a reader would otherwise mis-conclude ────────────────
    const warnings = [];
    // Leads the list on purpose. An unfinished run is worse than a failed one: it looks like a
    // result. There is no resume — the AI pass walks the session list once, and if the worker
    // stops (deploy, restart) the remaining sessions are simply never reviewed and nothing
    // retries them. Re-running is the only fix, and it starts from zero.
    if (rollup.notReviewed > 0) {
        warnings.push({
            level: 'red',
            text: 'INCOMPLETE RUN — ' + rollup.notReviewed + ' of ' + rollup.images + ' images were never reviewed'
                + (rollup.unstarted ? (', including ' + rollup.unstarted + ' FLW audit' + (rollup.unstarted === 1 ? '' : 's') + ' with no review at all') : '')
                + '. The AI pass stopped before finishing; it does not resume. Re-run to complete.',
        });
    }
    if (rollup.reviewed > 0 && rollup.errorPct >= 20) {
        warnings.push({
            level: 'red',
            text: rollup.errorPct + '% of AI calls errored (' + rollup.error + ' of ' + rollup.reviewed + '). '
                + 'Errored images were NOT reviewed — treat this run as incomplete, not as a clean result.',
        });
    }
    if (rollup.aiPending > 0) {
        warnings.push({
            level: 'amber',
            text: rollup.aiPending + ' assessment' + (rollup.aiPending === 1 ? '' : 's') + ' exist with no AI verdict — '
                + 'the image was extracted and queued but the agent returned nothing for it.',
        });
    }
    const unverifiedSel = selected.filter(id => meta(id).unverified);
    if (unverifiedSel.length) {
        warnings.push({
            level: 'amber',
            text: 'Scale hardware is UNCONFIRMED for ' + unverifiedSel.map(oppLabel).join(', ')
                + '. They default to the digital agent — verify before trusting their verdicts.',
        });
    }
    const mismatched = selected.filter(id => effectiveAgent(id) !== agentFor(id));
    if (mismatched.length) {
        warnings.push({
            level: 'amber',
            text: 'Agent overridden against scale hardware for ' + mismatched.map(oppLabel).join(', ')
                + '. A digital agent reading an analog dial false-fails almost everything.',
        });
    }
    const unknownAgents = selected.map(effectiveAgent).filter(a => !agentKnown(a));
    if (unknownAgents.length) {
        warnings.push({
            level: 'red',
            text: 'Agent(s) not present in this environment: ' + Array.from(new Set(unknownAgents)).join(', ')
                + '. Those audits will produce no verdicts.',
        });
    }

    // ── Small presentational helpers ──────────────────────────────────────────
    const Card = ({ label, value, sub, tone }) => (
        <div className={'bg-white rounded-lg shadow-sm p-4 border-l-4 ' + (tone || 'border-gray-200')}>
            <div className="text-2xl font-bold text-gray-900">{value}</div>
            <div className="text-xs font-medium text-gray-600 mt-0.5">{label}</div>
            {sub ? <div className="text-xs text-gray-400 mt-0.5">{sub}</div> : null}
        </div>
    );
    const ScalePill = ({ kind, unverified }) => (
        <span className={'inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold '
            + (kind === 'dial' ? 'bg-purple-100 text-purple-800' : 'bg-sky-100 text-sky-800')}
            title={kind === 'dial' ? 'Analog dial scale — scored by Scale [Dial]' : 'Digital LCD scale — scored by Scale [Digital]'}>
            {kind === 'dial' ? 'Dial' : 'Digital'}{unverified ? ' ?' : ''}
        </span>
    );
    const num = (n) => (n == null ? '—' : String(n));
    const pct = (a, b) => (b > 0 ? Math.round(100 * a / b) + '%' : '—');

    const byCountry = {};
    allOppIds.forEach(id => {
        const c = meta(id).country || 'Other';
        (byCountry[c] || (byCountry[c] = [])).push(id);
    });

    const hasCreated = sessions.length > 0;

    return (
        <div className="space-y-5 pb-10">
            {/* Header */}
            <div className="bg-white rounded-lg shadow-sm p-6">
                <h1 className="text-2xl font-bold text-gray-900">{definition.name}</h1>
                <p className="text-gray-600 mt-1 text-sm">{definition.description}</p>
                <div className="mt-3 flex flex-wrap gap-2 text-xs">
                    <span className="px-2 py-1 rounded bg-gray-100 text-gray-700">
                        Audited photo · <span className="font-mono">{WEIGHT_IMAGE_PATH}</span>
                    </span>
                    <span className="px-2 py-1 rounded bg-gray-100 text-gray-700">
                        Reading · <span className="font-mono">{WEIGHT_FIELD_PATH}</span>
                    </span>
                    <span className="px-2 py-1 rounded bg-amber-50 text-amber-800"
                        title="Registration weight photos sit at child_details/upload_weight_image and are not covered by this audit.">
                        Registration photos not audited
                    </span>
                </div>
            </div>

            {/* Warnings */}
            {warnings.length ? (
                <div className="space-y-2">
                    {warnings.map((w, i) => (
                        <div key={i} className={'rounded-lg px-4 py-3 text-sm border '
                            + (w.level === 'red' ? 'bg-red-50 border-red-200 text-red-800' : 'bg-amber-50 border-amber-200 text-amber-800')}>
                            <i className={'mr-2 fa-solid ' + (w.level === 'red' ? 'fa-circle-exclamation' : 'fa-triangle-exclamation')}></i>
                            {w.text}
                        </div>
                    ))}
                </div>
            ) : null}

            {/* Summary */}
            {hasCreated ? (
                <div>
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                        <Card label="FLW audits" value={num(rollup.flws)} sub={rollup.byOpp.length + ' opportunit' + (rollup.byOpp.length === 1 ? 'y' : 'ies')} tone="border-blue-400" />
                        <Card label="Weight photos" value={num(rollup.images)} sub="one per audited visit" tone="border-gray-300" />
                        <Card label="AI reviewed" value={num(rollup.reviewed)}
                            sub={rollup.notReviewed ? (rollup.notReviewed + ' never reviewed') : (pct(rollup.reviewed, rollup.images) + ' of photos')}
                            tone={rollup.notReviewed ? 'border-red-500' : 'border-indigo-400'} />
                        <Card label="Match" value={num(rollup.match)} sub={pct(rollup.match, rollup.scored) + ' of scored'} tone="border-green-500" />
                        <Card label="No match" value={num(rollup.noMatch)} sub={rollup.noMatchPct + '% of scored'} tone="border-amber-500" />
                        <Card label="Errored" value={num(rollup.error)} sub={rollup.errorPct + '% of attempts'} tone="border-red-500" />
                    </div>
                    <p className="text-xs text-gray-500 mt-2">
                        "Scored" = match + no-match, i.e. images the AI actually judged. Errors are not verdicts —
                        an errored image is unreviewed and still needs a human.
                    </p>
                </div>
            ) : null}

            {/* Per-LLO rollup */}
            {hasCreated ? (
                <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                    <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between flex-wrap gap-2">
                        <span className="text-sm font-semibold text-gray-800">Results by LLO</span>
                        <span className="text-xs text-gray-400">scale hardware decides which agent scored the photo</span>
                    </div>
                    <div className="overflow-x-auto">
                        <table className="min-w-full text-sm">
                            <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
                                <tr>
                                    {['LLO', 'Scale', 'Opps', 'FLWs', 'Photos', 'Reviewed', 'Match', 'No match', 'Errored', 'Never reviewed', 'Error %'].map((h, i) => (
                                        <th key={h} className={'px-3 py-2 font-medium whitespace-nowrap ' + (i < 2 ? 'text-left' : 'text-right')}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {rollup.byLlo.map(l => {
                                    const attempts = l.match + l.noMatch + l.error;
                                    const ep = attempts > 0 ? Math.round(100 * l.error / attempts) : 0;
                                    return (
                                        <tr key={l.llo} className="border-t border-gray-100">
                                            <td className="px-3 py-2 font-semibold text-gray-900 whitespace-nowrap">{l.llo}</td>
                                            <td className="px-3 py-2"><ScalePill kind={l.scale} /></td>
                                            <td className="px-3 py-2 text-right">{l.opps}</td>
                                            <td className="px-3 py-2 text-right">{l.sessions}</td>
                                            <td className="px-3 py-2 text-right">{l.images}</td>
                                            <td className="px-3 py-2 text-right">{l.assessed}</td>
                                            <td className="px-3 py-2 text-right text-green-700 font-semibold">{l.match}</td>
                                            <td className="px-3 py-2 text-right text-amber-700 font-semibold">{l.noMatch}</td>
                                            <td className="px-3 py-2 text-right text-red-700 font-semibold">{l.error}</td>
                                            <td className={'px-3 py-2 text-right font-semibold ' + (l.notReviewed ? 'text-red-700' : 'text-gray-300')}>{l.notReviewed || '—'}</td>
                                            <td className={'px-3 py-2 text-right font-semibold ' + (ep >= 20 ? 'text-red-700' : 'text-gray-600')}>{ep}%</td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>
            ) : null}

            {/* Configuration */}
            <div className="bg-white rounded-lg shadow-sm p-6 space-y-5">
                <div>
                    <div className="flex items-center justify-between flex-wrap gap-2">
                        <h3 className="text-sm font-semibold text-gray-800">
                            <i className="fa-solid fa-building-user mr-2 text-gray-400"></i>Opportunities
                            <span className="ml-2 text-xs font-normal text-gray-500">{selected.length} of {allOppIds.length} selected</span>
                        </h3>
                        <div className="flex flex-wrap gap-1.5 text-xs">
                            <button onClick={selectAll} className="px-2 py-1 rounded border border-gray-300 hover:border-blue-400">All</button>
                            <button onClick={selectNone} className="px-2 py-1 rounded border border-gray-300 hover:border-blue-400">None</button>
                            <button onClick={() => selectScale('digital')} className="px-2 py-1 rounded border border-sky-300 text-sky-700 hover:bg-sky-50">Digital only</button>
                            <button onClick={() => selectScale('dial')} className="px-2 py-1 rounded border border-purple-300 text-purple-700 hover:bg-purple-50">Dial only</button>
                        </div>
                    </div>
                    <div className="mt-3 space-y-4">
                        {Object.keys(byCountry).sort().map(country => (
                            <div key={country}>
                                <div className="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-1.5">{country}</div>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                                    {byCountry[country].map(id => {
                                        const m = meta(id);
                                        const on = selected.indexOf(id) >= 0;
                                        return (
                                            <label key={id} className={'flex items-center gap-2 rounded-lg border px-3 py-2 cursor-pointer '
                                                + (on ? 'border-blue-400 bg-blue-50' : 'border-gray-200 hover:border-gray-300')}>
                                                <input type="checkbox" checked={on} onChange={() => toggleOpp(id)} />
                                                <span className="text-sm font-medium text-gray-900">{m.llo}</span>
                                                <span className="text-xs text-gray-500">{m.version}</span>
                                                <span className="text-xs text-gray-400 font-mono">#{id}</span>
                                                <span className="ml-auto flex items-center gap-1.5">
                                                    <ScalePill kind={m.scale} unverified={m.unverified} />
                                                </span>
                                            </label>
                                        );
                                    })}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Agent routing */}
                {selected.length ? (
                    <div className="border-t border-gray-100 pt-4">
                        <h3 className="text-sm font-semibold text-gray-800 mb-2">
                            <i className="fa-solid fa-robot mr-2 text-gray-400"></i>AI agent per opportunity
                            <span className="ml-2 text-xs font-normal text-gray-500">defaults follow scale hardware</span>
                        </h3>
                        {agentsError ? (
                            <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2 mb-2">
                                Could not load the agent registry ({agentsError}). Defaults still apply.
                            </div>
                        ) : null}
                        <div className="overflow-x-auto">
                            <table className="min-w-full text-sm">
                                <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
                                    <tr>
                                        <th className="px-3 py-2 text-left font-medium">Opportunity</th>
                                        <th className="px-3 py-2 text-left font-medium">Scale</th>
                                        <th className="px-3 py-2 text-left font-medium">Agent</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {selected.map(id => (
                                        <tr key={id} className="border-t border-gray-100">
                                            <td className="px-3 py-2 whitespace-nowrap">{oppLabel(id)}</td>
                                            <td className="px-3 py-2"><ScalePill kind={scaleOf(id)} unverified={meta(id).unverified} /></td>
                                            <td className="px-3 py-2">
                                                <select
                                                    value={effectiveAgent(id)}
                                                    onChange={(e) => setAgentOverride(prev => Object.assign({}, prev, { [String(id)]: e.target.value }))}
                                                    className={'border rounded-lg px-2 py-1 text-sm '
                                                        + (effectiveAgent(id) === agentFor(id) ? 'border-gray-300' : 'border-amber-400 text-amber-800')}>
                                                    {(agents.length
                                                        ? agents.map(a => a.agent_id)
                                                        : [AGENT_FOR_SCALE.digital, AGENT_FOR_SCALE.dial]
                                                    ).map(aid => (
                                                        <option key={aid} value={aid}>{agentName(aid)}</option>
                                                    ))}
                                                </select>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                ) : null}

                {/* Window + scope */}
                <div className="border-t border-gray-100 pt-4">
                    <h3 className="text-sm font-semibold text-gray-800 mb-2">
                        <i className="fa-solid fa-calendar-week mr-2 text-gray-400"></i>Window and scope
                    </h3>
                    <div className="flex flex-wrap gap-2 mb-3">
                        {[['last_week', 'Last week'], ['last_7_days', 'Last 7 days'], ['last_14_days', 'Last 14 days'], ['last_30_days', 'Last 30 days'], ['custom', 'Custom']].map(p => (
                            <button key={p[0]} onClick={() => applyPreset(p[0])}
                                className={'px-3 py-1.5 text-sm rounded-full border '
                                    + (datePreset === p[0] ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-700 border-gray-300 hover:border-blue-400')}>
                                {p[1]}
                            </button>
                        ))}
                    </div>
                    <div className="flex flex-wrap items-end gap-4">
                        <div>
                            <label className="block text-xs text-gray-500 mb-1">Start</label>
                            <input type="date" value={startDate} max={endDate || undefined}
                                onChange={(e) => { setDatePreset('custom'); setStartDate(e.target.value); }}
                                className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm" />
                        </div>
                        <div>
                            <label className="block text-xs text-gray-500 mb-1">End</label>
                            <input type="date" value={endDate} min={startDate || undefined}
                                onChange={(e) => { setDatePreset('custom'); setEndDate(e.target.value); }}
                                className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm" />
                        </div>
                        <div>
                            <label className="block text-xs text-gray-500 mb-1"
                                title="Percentage of each FLW's qualifying visits to audit. Sampling is applied per FLW, so every worker keeps representation instead of the busiest crowding out the rest. 100 = census.">
                                Sample %
                            </label>
                            <div className="flex items-center gap-2">
                                <input type="number" min="1" max="100" value={samplePct}
                                    onChange={(e) => setSamplePct(Math.max(1, Math.min(100, Number(e.target.value) || 1)))}
                                    className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm w-20" />
                                <span className="text-xs text-gray-400">{Number(samplePct) >= 100 ? 'census' : 'per FLW'}</span>
                            </div>
                        </div>
                    </div>
                    <p className="text-xs text-gray-500 mt-3">
                        Sample % is the only volume control this backend honours for a date-range audit —
                        there is no cap on FLW count, and per-FLW visit limits apply only to "last N per FLW"
                        audits. Reduce the window or the percentage to keep a run small.
                    </p>
                </div>

                {/* Submit */}
                <div className="border-t border-gray-200 pt-4">
                    <button onClick={handleCreate}
                        disabled={!selected.length || !startDate || !endDate || isRunning}
                        title={!selected.length ? 'Select at least one opportunity' : (!startDate || !endDate ? 'Set a window' : '')}
                        className={'inline-flex items-center px-6 py-3 rounded-lg font-medium text-white '
                            + (!selected.length || !startDate || !endDate || isRunning ? 'bg-gray-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700')}>
                        <i className={'mr-2 fa-solid ' + (isRunning ? 'fa-spinner fa-spin' : 'fa-play')}></i>
                        {isRunning ? 'Creating…' : ('Create ' + selected.length + ' audit' + (selected.length === 1 ? '' : 's') + ' with AI')}
                    </button>
                    <p className="text-xs text-gray-500 mt-2">
                        Opportunities are audited <span className="font-medium">one after another</span>, not in parallel —
                        the scale classifiers degrade above roughly 20 concurrent calls, and each audit holds about 10
                        images in flight. Running five at once was measured at 77 usable classifications/hour against 644
                        for one at a time. The AI pass runs on the server, so you can leave this page.
                    </p>
                    {selected.length > 1 ? (
                        <p className="text-xs text-gray-500 mt-1">
                            <i className="fa-solid fa-clock mr-1 text-gray-400"></i>
                            {selected.length} opportunities queued sequentially. At the best observed rate for scale
                            classifiers (~650 photos/hour) expect roughly
                            <span className="font-medium"> {Math.max(1, Math.round(selected.length * 300 / 650))}–{Math.max(1, Math.round(selected.length * 900 / 650))} hours</span>
                            {' '}for a typical KMC window — reduce Sample % or the date range to shorten it.
                        </p>
                    ) : null}
                    {progress ? (
                        <div className={'mt-3 rounded-lg px-4 py-3 text-sm border '
                            + (progress.status === 'failed' ? 'bg-red-50 border-red-200 text-red-800'
                                : progress.status === 'completed' ? 'bg-green-50 border-green-200 text-green-800'
                                    : 'bg-blue-50 border-blue-200 text-blue-800')}>
                            <i className={'mr-2 fa-solid ' + (progress.status === 'failed' ? 'fa-circle-exclamation'
                                : progress.status === 'completed' ? 'fa-circle-check' : 'fa-spinner fa-spin')}></i>
                            {progress.message || progress.error || 'Working…'}
                            {progress.total ? <span className="ml-2 text-xs">({progress.processed || 0}/{progress.total})</span> : null}
                            <div className="mt-1 text-xs opacity-70">
                                Server message — it counts only passes and no-matches, so errored images are not
                                reflected in it. The live figures below are the real state.
                            </div>
                        </div>
                    ) : null}

                    {/* Live state, computed from the sessions actually written so far. Refreshes every
                        20s while a run is in flight, so a run that is failing looks like it is failing. */}
                    {(isRunning || rollup.reviewed > 0) ? (
                        <div className="mt-3 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
                            <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
                                <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                                    {isRunning ? 'Live — refreshing every 20s' : 'Result'}
                                </span>
                                <button onClick={refreshSessions} className="text-xs underline text-gray-500 hover:text-gray-800">
                                    refresh now
                                </button>
                            </div>
                            <div className="flex flex-wrap items-center gap-2 text-sm">
                                <span className="px-2 py-1 rounded bg-white border border-gray-200">
                                    <span className="font-semibold">{rollup.reviewed}</span>
                                    <span className="text-gray-500"> of {rollup.images} photos reviewed</span>
                                </span>
                                <span className="px-2 py-1 rounded bg-green-50 text-green-800 border border-green-200">
                                    <span className="font-semibold">{rollup.match}</span> match
                                </span>
                                <span className="px-2 py-1 rounded bg-amber-50 text-amber-800 border border-amber-200">
                                    <span className="font-semibold">{rollup.noMatch}</span> no match
                                </span>
                                <span className={'px-2 py-1 rounded border '
                                    + (rollup.error ? 'bg-red-50 text-red-800 border-red-200' : 'bg-white text-gray-400 border-gray-200')}>
                                    <span className="font-semibold">{rollup.error}</span> errored
                                    {rollup.reviewed ? <span className="ml-1">({rollup.errorPct}%)</span> : null}
                                </span>
                                {rollup.notReviewed ? (
                                    <span className="px-2 py-1 rounded bg-red-50 text-red-800 border border-red-200">
                                        <span className="font-semibold">{rollup.notReviewed}</span> never reviewed
                                    </span>
                                ) : null}
                            </div>
                            {rollup.reviewed > 0 && rollup.errorPct >= 20 ? (
                                <div className="mt-2 text-xs text-red-700">
                                    Most calls are failing. Errored photos get no verdict and still need a human —
                                    this run will not give a usable read on scale-photo quality.
                                </div>
                            ) : null}
                        </div>
                    ) : null}
                    {runError ? (
                        <div className="mt-3 rounded-lg px-4 py-3 text-sm border bg-red-50 border-red-200 text-red-800">{runError}</div>
                    ) : null}
                </div>
            </div>

            {/* Per-opportunity detail */}
            {hasCreated ? (
                <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                    <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between flex-wrap gap-2">
                        <span className="text-sm font-semibold text-gray-800">Per-opportunity detail</span>
                        <button onClick={refreshSessions} className="text-xs underline text-gray-500 hover:text-gray-800">
                            {loadingSessions ? 'Refreshing…' : 'Refresh'}
                        </button>
                    </div>
                    <div className="overflow-x-auto">
                        <table className="min-w-full text-sm">
                            <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
                                <tr>
                                    {['Opportunity', 'Scale', 'Agent', 'FLWs', 'Photos', 'Reviewed', 'Match', 'No match', 'Errored', 'Never reviewed'].map((h, i) => (
                                        <th key={h} className={'px-3 py-2 font-medium whitespace-nowrap ' + (i < 3 ? 'text-left' : 'text-right')}
                                            title={h === 'Never reviewed' ? 'Images the AI pass never reached — not a verdict, not an error. Caused by the task stopping before it finished.' : undefined}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {rollup.byOpp.map(o => (
                                    <tr key={o.opp} className="border-t border-gray-100 hover:bg-gray-50">
                                        <td className="px-3 py-2 whitespace-nowrap">
                                            <span className="font-medium text-gray-900">{o.llo}</span>
                                            <span className="text-xs text-gray-500 ml-1">{meta(o.opp).version}</span>
                                            <span className="text-xs text-gray-400 font-mono ml-1">#{o.opp}</span>
                                        </td>
                                        <td className="px-3 py-2"><ScalePill kind={o.scale} unverified={meta(o.opp).unverified} /></td>
                                        <td className="px-3 py-2 text-xs text-gray-600 whitespace-nowrap">{agentName(effectiveAgent(o.opp))}</td>
                                        <td className="px-3 py-2 text-right">{o.sessions}</td>
                                        <td className="px-3 py-2 text-right">{o.images}</td>
                                        <td className="px-3 py-2 text-right">{o.assessed}</td>
                                        <td className="px-3 py-2 text-right text-green-700">{o.match}</td>
                                        <td className="px-3 py-2 text-right text-amber-700">{o.noMatch}</td>
                                        <td className="px-3 py-2 text-right text-red-700">{o.error}</td>
                                        <td className={'px-3 py-2 text-right font-semibold ' + (o.notReviewed ? 'text-red-700' : 'text-gray-300')}
                                            title={o.unstarted ? (o.unstarted + ' FLW audit(s) here were never started') : undefined}>
                                            {o.notReviewed ? o.notReviewed + (o.unstarted ? ' (' + o.unstarted + ' FLWs)' : '') : '—'}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    <div className="px-4 py-2 text-xs text-gray-500">
                        {sessions.length} session{sessions.length === 1 ? '' : 's'} across {rollup.byOpp.length} opportunit{rollup.byOpp.length === 1 ? 'y' : 'ies'} ·
                        counts read from the stored session records, not from the create response.
                    </div>
                </div>
            ) : null}

            {/* Sessions list */}
            {hasCreated ? (
                <div className="bg-white rounded-lg shadow-sm p-6">
                    <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
                        <div className="text-sm font-semibold text-gray-800">
                            Audit sessions — open a field worker's photos
                        </div>
                        <div className="text-xs text-gray-400">grouped by opportunity · worst first</div>
                    </div>
                    {/* Deliberately NOT window.LabsAudit.renderFlwBreakdown. That shared component is
                        built for the dual-track model and keys off sessions tagged 'muac' / 'rest';
                        against our 'kmc_weight_photo' tag it reported "MUAC: not created / Other:
                        not created" for every FLW and rendered no links at all. */}
                    <div className="space-y-5">
                        {rollup.byOpp.map(o => {
                            const rows = sessions
                                .filter(s => (s._opp || s.opportunity_id) === o.opp)
                                .map(s => {
                                    const st = s.assessment_stats || {};
                                    const photos = s.visit_count || 0;
                                    const gap = Math.max(0, photos - (st.total || 0));
                                    return {
                                        s: s, photos: photos, gap: gap,
                                        match: st.ai_match || 0, noMatch: st.ai_no_match || 0, error: st.ai_error || 0,
                                        humanDone: (st.pass || 0) + (st.fail || 0),
                                    };
                                })
                                // Worst first: never-reviewed, then no-match (the ones a human must
                                // actually look at), then errors.
                                .sort((a, b) => (b.gap - a.gap) || (b.noMatch - a.noMatch) || (b.error - a.error)
                                    || String(a.s.flw_display_name || '').localeCompare(String(b.s.flw_display_name || '')));
                            return (
                                <div key={o.opp}>
                                    <div className="flex items-center gap-2 mb-1.5">
                                        <span className="text-sm font-semibold text-gray-900">{o.llo}</span>
                                        <span className="text-xs text-gray-500">{meta(o.opp).version} · {meta(o.opp).country}</span>
                                        <span className="text-xs text-gray-400 font-mono">#{o.opp}</span>
                                        <ScalePill kind={o.scale} unverified={meta(o.opp).unverified} />
                                        <span className="text-xs text-gray-400">{rows.length} field worker{rows.length === 1 ? '' : 's'}</span>
                                    </div>
                                    <div className="overflow-x-auto border border-gray-100 rounded-lg">
                                        <table className="min-w-full text-sm">
                                            <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
                                                <tr>
                                                    <th className="px-3 py-2 text-left font-medium">Field worker</th>
                                                    <th className="px-3 py-2 text-right font-medium">Photos</th>
                                                    <th className="px-3 py-2 text-right font-medium">Match</th>
                                                    <th className="px-3 py-2 text-right font-medium">No match</th>
                                                    <th className="px-3 py-2 text-right font-medium">Errored</th>
                                                    <th className="px-3 py-2 text-right font-medium">Never reviewed</th>
                                                    <th className="px-3 py-2 text-left font-medium">Status</th>
                                                    <th className="px-3 py-2 text-right font-medium">Images</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {rows.map(r => (
                                                    <tr key={r.s.id} className="border-t border-gray-100 hover:bg-gray-50">
                                                        <td className="px-3 py-2 whitespace-nowrap">
                                                            <span className="font-medium text-gray-900">
                                                                {r.s.flw_display_name || r.s.flw_username || ('Session ' + r.s.id)}
                                                            </span>
                                                            {r.noMatch > 0
                                                                ? <span className="ml-2 px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 text-xs font-semibold"
                                                                    title="The AI says the photo does not match the typed weight — review these first.">
                                                                    {r.noMatch} to check
                                                                </span>
                                                                : null}
                                                        </td>
                                                        <td className="px-3 py-2 text-right">{r.photos}</td>
                                                        <td className="px-3 py-2 text-right text-green-700">{r.match || '—'}</td>
                                                        <td className={'px-3 py-2 text-right font-semibold ' + (r.noMatch ? 'text-amber-700' : 'text-gray-300')}>{r.noMatch || '—'}</td>
                                                        <td className={'px-3 py-2 text-right ' + (r.error ? 'text-red-700' : 'text-gray-300')}>{r.error || '—'}</td>
                                                        <td className={'px-3 py-2 text-right font-semibold ' + (r.gap ? 'text-red-700' : 'text-gray-300')}
                                                            title={r.gap ? 'The AI pass never reached these photos' : undefined}>{r.gap || '—'}</td>
                                                        <td className="px-3 py-2 text-xs">
                                                            <span className={'px-2 py-0.5 rounded font-semibold '
                                                                + (r.s.status === 'completed' ? 'bg-green-100 text-green-800' : 'bg-blue-100 text-blue-800')}>
                                                                {r.s.status || 'open'}
                                                            </span>
                                                            {r.humanDone ? <span className="ml-1 text-gray-400">{r.humanDone} human-marked</span> : null}
                                                        </td>
                                                        <td className="px-3 py-2 text-right whitespace-nowrap">
                                                            <a className="text-xs font-medium text-blue-600 hover:underline"
                                                                href={'/audit/' + r.s.id + '/bulk/?opportunity_id=' + o.opp}
                                                                target="_blank" rel="noopener noreferrer"
                                                                title="Open this field worker's photos for this run">
                                                                Open images →
                                                            </a>
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            ) : null}
        </div>
    );
}
"""

TEMPLATE = {
    "key": "kmc_image_audit",
    "name": DEFINITION["name"],
    "description": DEFINITION["description"],
    "icon": "fa-weight-scale",
    "color": "purple",
    "multi_opp": True,
    "supports_saved_runs": False,
    "definition": DEFINITION,
    "render_code": RENDER_CODE,
}
