"""
KMC Audit Dashboard workflow template (multi-opportunity, action-shaped).

Register-faithful rewrite: computes the 18 FLW-Audit metrics from the
"KMC Audit & Metrics Flag Register (all)" spec, each rendered as a 3-tier RAG
band (GREEN / YELLOW / RED / NE) with its value and numerator/denominator, over
MERGED V1+V2 opportunity data (rows tagged with opportunity_id; the render merges
them per (LLO, username)).

Two pipelines (connect_csv):
- ``flw_flags``     AGGREGATED — per-FLW total_cases (exclusion gate).
- ``weight_series`` VISIT_LEVEL — per-visit rows for the 18 metrics (weight pairs,
  mortality, enrollment incl. home births, danger/referral, vitals, GPS,
  equipment image, KMC wrap, early discharge).

The render's compute core (deriveMetrics + groupCases + helpers) is BYTE-IDENTICAL
to ``.kmc_validation/register/kmc_flags.js`` and proven equal to the Python
reference engine (``engine.py``) by ``parity.js`` — 730 assertions (bands exact,
values 1e-9, num/den exact), PASS. Do NOT edit the compute core without re-running
that parity harness.

Field paths resolved live from the V3 deliver app (opp 1487):
kmc_status_entered=form.kmc_status_entered; birth_location=form.hosp_lbl.birth_location;
child_dob=form.mothers_details.child_DOB; relocation=form.address_change_grp.relocation_followup_check;
equipment_image=form.danger_signs_checklist.equipment_image_capture_checklist.equipments_image_capture;
kmc_wrap=form.commodities_delivered.kmc_wrap_provided_check.
"""

PIPELINE_SCHEMAS = [
    {
        "alias": "flw_flags",
        "name": "KMC Audit — FLW Aggregated",
        "description": "Per-FLW aggregated counts: distinct cases (exclusion gate) + visit/danger counts",
        "schema": {
            "data_source": {"type": "connect_csv"},
            "grouping_key": "username",
            "terminal_stage": "aggregated",
            "linking_field": "beneficiary_case_id",
            "fields": [
                {
                    "name": "total_cases",
                    "paths": ["form.child_case_id", "form.kmc_beneficiary_case_id", "form.case.@case_id"],
                    "aggregation": "count_distinct",
                    # NAIVE count — do not trust it. In the V3 apps the 'Child Registration Form'
                    # keys to the mother case, an id disjoint from the child's visit rows, so this
                    # over-counts by +81% (1487) to +94% (1790). Dropping form.case.@case_id is NOT
                    # the fix: it would also drop legitimately registered-never-visited V1/V2 cases.
                    # The dashboard IGNORES this value and recomputes via correctedCaseCount().
                    "description": "Distinct beneficiary case IDs (NAIVE — V3 double-counts; render recomputes)",
                },
                {
                    "name": "kmc_visit_count",
                    # form.kmc_visit_number is the V0 shape — without it opp 675 reports 0 visits
                    # and 520 rows in 523/524 are invisible in the per-opportunity breakdown.
                    "paths": ["form.grp_kmc_visit.visit_number", "form.kmc_visit_number"],
                    "aggregation": "count",
                    "description": "KMC visits where visit_number is populated",
                },
                # danger_visit_count / danger_positive_count REMOVED (2026-08-07). Both were unread
                # by the render (which recomputes danger from the visit-level pipeline) and both were
                # wrong: they modelled 2 of the 4 danger_signs_checklist group spellings, and
                # danger_positive_count's filter_path takes a single path while the counted
                # expression COALESCEd across all of them — so the numerator counted visit-form rows
                # against a visit+registration denominator, undercounting by 28% (874) to 97% (1739).
                # filter_path has no multi-path form, so the field cannot be made correct; a wrong
                # published field is worse than no field.
            ],
            "histograms": [],
            "filters": {},
        },
    },
    {
        "alias": "weight_series",
        "name": "KMC Audit — Visit Level",
        "description": "Per-visit rows for the 18 register FLW-audit metrics",
        "schema": {
            "data_source": {"type": "connect_csv"},
            "grouping_key": "username",
            "terminal_stage": "visit_level",
            "linking_field": "beneficiary_case_id",
            "fields": [
                {
                    "name": "beneficiary_case_id",
                    "paths": ["form.child_case_id", "form.kmc_beneficiary_case_id", "form.case.@case_id"],
                    "aggregation": "first",
                },
                {
                    # form.visit_date is the pre-grp_kmc_visit (V0) shape: 100% of opp 675's
                    # visits plus 74 (523) + 446 (524) old-shape rows carry it and nothing else.
                    "name": "visit_date",
                    "paths": ["form.grp_kmc_visit.visit_date", "form.visit_date"],
                    "aggregation": "first",
                    "transform": "date",
                },
                {
                    "name": "weight",
                    "paths": [
                        "form.anthropometric.child_weight_visit",
                        "form.child_details.birth_weight_reg.child_weight_reg",
                        # V0 shape (opp 675): visit weight, then registration birth weight
                        "form.anthropometric.child_weight",
                        "form.child_details.birth_weight",
                    ],
                    "aggregation": "first",
                    "transform": "float",
                },
                {
                    # V0 shape: without this fallback opp 675 extracts ZERO visits (all 327 of
                    # its follow-ups were read as registration rows) and 520 more are lost in
                    # 523/524 — they vanish from every visit-denominated metric.
                    "name": "visit_number",
                    "paths": ["form.grp_kmc_visit.visit_number", "form.kmc_visit_number"],
                    "aggregation": "first",
                    "transform": "int",
                },
                {
                    "name": "reg_date",
                    "paths": ["form.reg_date", "form.grp_kmc_beneficiary.reg_date"],
                    "aggregation": "first",
                    "transform": "date",
                },
                {
                    "name": "discharge_date",
                    "path": "form.hosp_lbl.date_hospital_discharge",
                    "aggregation": "first",
                    "transform": "date",
                },
                {
                    "name": "kmc_status",
                    "paths": [
                        "form.grp_kmc_beneficiary.kmc_status",
                        "form.child_eligibility.kmc_status",
                        "form.kmc_status",
                    ],
                    "aggregation": "first",
                },
                {
                    # Four group-name shapes exist in production, not two. The last two below
                    # recover 326 rows in 675 (65% of that opp) + 226 in 523/524. Deliberately
                    # NOT falling back to form.case.update.* here: case properties carry forward
                    # between visits, so a stale "yes" would forge danger-sign history.
                    "name": "danger_sign_positive",
                    "paths": [
                        "form.danger_signs_checklist.danger_sign_positive",
                        "form.child_details.Danger_Signs_Checklist.danger_sign_positive",
                        "form.Danger_Signs_Checklist.danger_sign_positive",
                        "form.child_details.danger_signs_checklist.danger_sign_positive",
                    ],
                    "aggregation": "first",
                },
                {"name": "child_alive", "path": "form.child_alive", "aggregation": "first"},
                {
                    "name": "child_referred",
                    "paths": [
                        "form.danger_signs_checklist.child_referred",
                        "form.child_details.Danger_Signs_Checklist.child_referred",
                        "form.case.update.child_referred",
                    ],
                    "aggregation": "first",
                },
                {
                    "name": "temperature",
                    "paths": [
                        "form.danger_signs_checklist.temp_grp.svn_temperature",
                        "form.child_details.Danger_Signs_Checklist.temp_grp.svn_temperature",
                        "form.danger_signs_checklist.svn_temperature",
                        "form.child_details.Danger_Signs_Checklist.svn_temperature",
                        "form.Danger_Signs_Checklist.svn_temperature",
                        "form.child_details.danger_signs_checklist.svn_temperature",
                    ],
                    "aggregation": "first",
                    "transform": "float",
                },
                {
                    # form.gps_block.normalized_location is the V3 apps' own GPS block: it carries
                    # 527 rows (198 follow-ups) where none of the first three paths fire, and where
                    # both exist the strings are identical on 8,393 rows — same reading, better
                    # coverage. Last in the list, so it can only fill nulls.
                    "name": "gps",
                    "paths": [
                        "form.visit_gps_manual",
                        "form.reg_gps",
                        "metadata.location",
                        "form.gps_block.normalized_location",
                    ],
                    "aggregation": "first",
                },
                {
                    # The baby's case id, created as a subcase by the V3 Child Registration Form.
                    # Present on 100% of CRF rows; without it registrations key to the MOTHER, which
                    # collapses twins and strands the birth weight on a case that has no visits.
                    "name": "child_subcase_id",
                    "path": "form.subcase_0.case.@case_id",
                    "aggregation": "first",
                },
                {
                    # The ONLY reliable discriminator for an "Additional Visit": its visit_number is
                    # the literal string "Additional", which the int transform nulls, so without this
                    # field 481 real visits are misread as registrations.
                    "name": "visit_type",
                    "path": "form.grp_kmc_visit.visit_type",
                    "aggregation": "first",
                },
                {
                    "name": "heart_rate",
                    "paths": [
                        "form.danger_signs_checklist.child_heart_rate",
                        "form.child_details.Danger_Signs_Checklist.child_heart_rate",
                        "form.Danger_Signs_Checklist.child_heart_rate",
                        "form.child_details.danger_signs_checklist.child_heart_rate",
                    ],
                    "aggregation": "first",
                    "transform": "float",
                },
                {
                    "name": "spo2_level",
                    "paths": [
                        "form.danger_signs_checklist.spo2_level",
                        "form.child_details.Danger_Signs_Checklist.spo2_level",
                    ],
                    "aggregation": "first",
                    "transform": "float",
                },
                # ---- register-metric fields (added for the banded rewrite) ----
                {
                    "name": "kmc_status_entered",
                    "path": "form.kmc_status_entered",
                    "aggregation": "first",
                },
                {
                    "name": "flw_program_conclusion_reason",
                    "paths": [
                        "form.flw_program_conclusion_reason",
                        "form.case.update.flw_program_conclusion_reason",
                    ],
                    "aggregation": "first",
                },
                {
                    "name": "birth_location",
                    "path": "form.hosp_lbl.birth_location",
                    "aggregation": "first",
                },
                {
                    "name": "child_dob",
                    # opp 675 records DOB only as a case property (immutable, so no staleness risk)
                    "paths": ["form.mothers_details.child_DOB", "form.child_DOB", "form.case.update.child_DOB"],
                    "aggregation": "first",
                    "transform": "date",
                },
                {
                    "name": "relocation_followup_check",
                    "path": "form.address_change_grp.relocation_followup_check",
                    "aggregation": "first",
                },
                {
                    "name": "location_change",
                    "path": "form.address_change_grp.location_change_proceed_check",
                    "aggregation": "first",
                },
                {
                    "name": "equipment_image",
                    "path": "form.danger_signs_checklist.equipment_image_capture_checklist.equipments_image_capture",
                    "aggregation": "first",
                },
                {
                    "name": "kmc_wrap_check",
                    "path": "form.commodities_delivered.kmc_wrap_provided_check",
                    "aggregation": "first",
                },
                # ---- V3 case-count fix (match Superset KMC_Cases_Optimized) ----
                {"name": "form_name", "path": "form.@name", "aggregation": "first"},
                {
                    "name": "eligibility_status",
                    "path": "form.child_eligibility.eligibility_status",
                    "aggregation": "first",
                },
            ],
            "histograms": [],
            "filters": {},
        },
    },
]

DEFINITION = {
    "name": "KMC Audit Dashboard",
    "description": (
        "18-metric register-faithful KMC FLW audit across 11 opportunities / 6 LLOs / 3 countries "
        "(V0–V3, live). 3-tier RAG bands, exec Overview + per-FLW drilldown, one-click audit creation."
    ),
    "version": 3,
    "templateType": "kmc_audit_dashboard",
    "statuses": [
        {"id": "pending", "label": "Pending Review", "color": "gray"},
        {"id": "audits_created", "label": "Audits Created", "color": "green"},
    ],
    "config": {"multi_opp": True, "showSummaryCards": False, "showFilters": False},
    "pipeline_sources": [],
}

RENDER_CODE = r"""/* KMC Audit Dashboard — RENDER_CODE (register-faithful banded RAG, multi-opp, live).
 * Compute core (deriveMetrics + groupCases + helpers) is byte-identical to
 * .kmc_validation/register/kmc_flags.js and proven == engine.py by parity.js
 * (bands exact, values 1e-9, num/den exact). Re-run parity before editing it.
 * 18 FLW-Audit metrics per "KMC Audit & Metrics Flag Register (all)".
 */

// ============================= compute core (PARITY-LOCKED) =============================
var WMIN = 500.0, WMAX = 5000.0, PAIR_MIN = 1, PAIR_MAX = 30, KG_TO_G = 1000.0;
var DAY_MS = 86400000, EARTH_R_M = 6371000.0;
// Caseload below which an FLW is LABELLED low-caseload. NOT an exclusion: the register sets a
// minimum per metric (5 to 30) and nowhere authorises a global gate. Excluding on 20 cases
// suppressed 272 metric cells that clear their own register minimum, 73 of them RED.
var LOW_CASELOAD_CASES = 20;
// fields that exist in only SOME app versions, so their denominators must be scoped
// Fields whose presence is a property of the APP (0% or 82-100% per opportunity), so a global
// map is right. The discharge-reason fields are NOT here: per opportunity they run 87-100%,
// i.e. presence is per-WORKER, and absence there yields the BEST band.
var SCOPED_FIELDS = ["equipment_image", "kmc_wrap_check"];

var METRIC_KEYS = ["low_avg_visits","mortality","enroll_ontime","zero_danger","danger_rate_cases",
  "no_referral","weight_loss","weight_gain_gkgday","rounded_weights","modal_weight","flat_weight",
  "gps_within_200m","hr_copycat","temp_copycat","spo2_implausible","image_missing","flw_early_discharge","kmc_wrap_missing"];
var PRIORITY = {low_avg_visits:1,mortality:1,enroll_ontime:1,zero_danger:1,no_referral:1,rounded_weights:1,
  gps_within_200m:1,hr_copycat:1,temp_copycat:1,spo2_implausible:1,flw_early_discharge:1,
  danger_rate_cases:2,weight_loss:2,weight_gain_gkgday:2,modal_weight:2,flat_weight:2,image_missing:2,kmc_wrap_missing:2};

function rget(row, key){ if(row==null) return null; var v=row[key]; return v===undefined?null:v; }
function pf(v){ if(v===null||v===undefined||v===""||typeof v==="boolean") return null; var f=Number(v); return isNaN(f)?null:f; }
function pint(v){ if(v===null||v===undefined||v==="") return null; var f=Number(v); return isNaN(f)?null:Math.trunc(f); }
function low(v){ return (v===null||v===undefined||v==="")?null:String(v).trim().toLowerCase(); }
function rnd(x){ return Math.floor(x+0.5); }
function parseDate(v){
  if(v===null||v===undefined||v==="") return null;
  var s=String(v).slice(0,10);
  var m=/^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if(!m) return null;
  return Date.UTC(parseInt(m[1],10),parseInt(m[2],10)-1,parseInt(m[3],10));
}
function daysBetween(a,b){ return Math.round((b-a)/DAY_MS); }
function readWeightG(row){ var w=pf(rget(row,"weight")); if(w===null||w<=0) return null; if(w<50) return w*KG_TO_G; if(w>=100&&w<=10000) return w; return null; }
function parseGps(raw){
  if(raw===null||raw===undefined||typeof raw!=="string") return null;
  var p=raw.trim().split(/\s+/); if(p.length<2) return null;
  var lat=pf(p[0]), lon=pf(p[1]); var acc=p.length>3?pf(p[3]):null;
  if(lat===null||lon===null) return null;
  if(!(lat>=-90&&lat<=90&&lon>=-180&&lon<=180)) return null;
  if(lat===0.0&&lon===0.0) return null;
  return [lat,lon,acc];
}
function haversineM(a,b){
  var toR=Math.PI/180, la1=a[0]*toR, lo1=a[1]*toR, la2=b[0]*toR, lo2=b[1]*toR;
  var hh=Math.sin((la2-la1)/2)*Math.sin((la2-la1)/2)+Math.cos(la1)*Math.cos(la2)*Math.sin((lo2-lo1)/2)*Math.sin((lo2-lo1)/2);
  return 2*EARTH_R_M*Math.asin(Math.sqrt(hh));
}
function median(arr){ var a=arr.slice().sort(function(x,y){return x-y;}); var n=a.length; if(n===0) return null; var mid=Math.floor(n/2); return n%2?a[mid]:(a[mid-1]+a[mid])/2; }
function modalCount(vals){ var c={}, top=0; for(var i=0;i<vals.length;i++){ var k=String(vals[i]); c[k]=(c[k]||0)+1; if(c[k]>top) top=c[k]; } return top; }
function ragLowBad(v,g,y){ if(v===null) return "N/A"; if(v>=g) return "GREEN"; if(v>=y) return "YELLOW"; return "RED"; }
function ragHighBad(v,g,y){ if(v===null) return "N/A"; if(v<g) return "GREEN"; if(v<=y) return "YELLOW"; return "RED"; }
function M(value,rag,num,den){ return {value:value,rag:rag,num:(num===undefined?null:num),den:(den===undefined?null:den)}; }
function NA(){ return {value:null,rag:"N/A",num:null,den:null}; }

// The case a row belongs to. In the V3 apps the Child Registration Form is filled against the
// MOTHER and creates a subcase for the baby, so its own case.@case_id is the mother's — disjoint
// from the baby's visit rows. That produced a reg-only "phantom" case per baby AND collapsed TWINS
// into one record (231 real twin pairs live). The registration row carries the baby's case id at
// form.subcase_0.case.@case_id on 100% of rows, so key on that. Conditional on the form on purpose:
// 'Register KMC Beneficiary' rows in opps 523/675 also carry a subcase_0 and must NOT be re-keyed.
var _RICH_FIELDS=["weight","danger_sign_positive","temperature","heart_rate","spo2_level","gps","equipment_image","child_referred","child_alive"];
// How much clinical content a row carries - picks the survivor on a dedup collision so a blank
// resubmission never displaces a complete one (last-wins destroyed real weights and vitals).
function _richness(row){ var n=0,i; for(i=0;i<_RICH_FIELDS.length;i++){ var v=rget(row,_RICH_FIELDS[i]); if(v!==null&&v!==undefined&&v!=="") n++; } return n; }

function caseIdOf(row){
  if(low(rget(row,"form_name"))==="child registration form"){
    var sub=rget(row,"child_subcase_id");
    if(sub!==null&&sub!==undefined&&sub!=="") return String(sub);
  }
  return rget(row,"beneficiary_case_id");
}

function groupCases(visitRows){
  var by={}, i, r, cid;
  for(i=0;i<visitRows.length;i++){ r=visitRows[i]; cid=caseIdOf(r); if(!cid) continue; cid=String(cid); (by[cid]=by[cid]||[]).push(r); }
  var cases=[];
  Object.keys(by).forEach(function(cid){
    var rows=by[cid];
    var regDates=[]; for(i=0;i<rows.length;i++){ var d=parseDate(rget(rows[i],"reg_date")); if(d!==null) regDates.push(d); }
    var regDate=regDates.length?Math.min.apply(null,regDates):null;
    function first(field,tf){ for(var j=0;j<rows.length;j++){ var v=rget(rows[j],field); if(v!==null&&v!==""){ return tf?tf(v):v; } } return null; }
    var dischargeDate=first("discharge_date",parseDate);
    var dob=first("child_dob",parseDate);
    var birthLocation=first("birth_location",low);
    // follow-ups: a numbered visit OR an "Additional Visit", plus a parseable visit_date. An
    // additional visit carries the literal string "Additional" in visit_number, which the pipeline's
    // int transform nulls — without the visit_type test these rows were read as REGISTRATIONS and
    // 481 real visits (479 GPS points, 100 danger-sign assessments, 46 weights) vanished from every
    // follow-up metric, leaving 10 cases looking 0-visit.
    var fus=[], regRows=[];
    for(i=0;i<rows.length;i++){
      var _vn=pint(rget(rows[i],"visit_number"));
      var _isAdd=low(rget(rows[i],"visit_type"))==="additional visit";
      if(_vn===null&&!_isAdd){ regRows.push(rows[i]); continue; }
      var vd=parseDate(rget(rows[i],"visit_date")); if(vd===null) continue;
      // Dedup key: visit number for scheduled visits; the date for additional ones (they have no
      // number). 24 cases have MORE THAN ONE additional visit, so a shared sentinel would collapse
      // them; the date keeps them distinct while still deduping a same-day resubmission.
      fus.push([vd,(_vn!==null)?("N:"+_vn):("A:"+rget(rows[i],"visit_date")),rows[i]]);
    }
    fus.sort(function(a,b){ return a[0]-b[0]; });
    var _byKey={};
    for(i=0;i<fus.length;i++){ var _pv=_byKey[fus[i][1]]; if(!_pv||_richness(fus[i][2])>=_richness(_pv[2])) _byKey[fus[i][1]]=fus[i]; }
    fus=Object.keys(_byKey).map(function(kk){return _byKey[kk];}); fus.sort(function(a,b){ return a[0]-b[0]; });
    var followups=fus.map(function(t){return t[2];});
    var followupDates=fus.map(function(t){return t[0];});
    var nAdditional=0; for(i=0;i<followups.length;i++){ if(low(rget(followups[i],"visit_type"))==="additional visit") nAdditional++; }
    var lastVisitDate=null;
    for(i=0;i<rows.length;i++){ var dd=parseDate(rget(rows[i],"visit_date")); if(dd!==null&&(lastVisitDate===null||dd>lastVisitDate)) lastVisitDate=dd; }
    var isDeath=false; for(i=0;i<rows.length;i++){ if(low(rget(rows[i],"child_alive"))==="no"){ isDeath=true; break; } }
    var statusEntered={}; for(i=0;i<rows.length;i++){ var se=low(rget(rows[i],"kmc_status_entered")); if(se) statusEntered[se]=1; }
    var conclusionReason=null; for(i=0;i<rows.length;i++){ var cr0=low(rget(rows[i],"flw_program_conclusion_reason")); if(cr0){ conclusionReason=cr0; break; } }
    // V3 phantom-case guard: the "Child Registration Form" keys to the mother case (id disjoint
    // from the child's follow-up case), forming a reg-only 0-follow-up case. Exclude it from the
    // follow-up-engagement metrics (low_avg_visits, flw_early_discharge) so it can't ~double their
    // denominators. Still kept for enroll_ontime / kmc_wrap (which read reg-row data).
    var isCrf=false; for(i=0;i<rows.length;i++){ if(low(rget(rows[i],"form_name"))==="child registration form"){ isCrf=true; break; } }
    // Did this case EXIT the programme early (register row 19's four reasons)? Computed once
    // so flw_early_discharge (which scores it) and low_avg_visits (which must exclude it) can
    // never drift apart: an early-exited case had its exposure cut short, so counting it in the
    // visits-per-case denominator penalises the FLW twice for one event. A case that RAN ITS
    // COURSE and graduated (recovered with >=4 visits) is NOT early — those are 49.3% of the
    // eligible denominator and carry MORE visits, so excluding them would manufacture REDs.
    // Two flavours, deliberately separated. isExitExogenous = the case left for a reason outside
    // the FLW's control, so it could not accumulate visits -> excluded from low_avg_visits, the
    // same logic the register applies to deaths. isEarly = all four register reasons, used by
    // flw_early_discharge which SCORES the behaviour. The 'recovered before visit 4' leg must NOT
    // reach low_avg_visits: removing a case for having too few visits, from the metric that
    // measures too few visits, is circular and hid real flags.
    var isExitExogenous=(statusEntered["parents_discontinued"]||conclusionReason==="caregiver_unavailable"
      ||conclusionReason==="family_relocated")?true:false;
    // "discharged before visit 4" is about the SCHEDULED schedule; counting additional visits
    // here cancelled 89 early-discharge flags (one FLW went 20/39 RED -> 1/39 GREEN).
    var nScheduled=followups.length-nAdditional;
    var isEarly=(isExitExogenous
      ||(conclusionReason==="svn_recovered_or_met_discharge_criteria"&&nScheduled<4))?true:false;
    // Weight series (reg + follow-ups). Registration rows carry no grp_kmc_visit.visit_date, so
    // without the reg_date fallback the enrolment weight — the birth anchor where neonatal weight
    // loss shows up — never entered the series (5,799 points across the 11 opps). Only reg rows
    // (visit_number null) fall back, so no row can be dated twice.
    var ws=[];
    for(i=0;i<rows.length;i++){ var vd2=parseDate(rget(rows[i],"visit_date")); if(vd2===null&&pint(rget(rows[i],"visit_number"))===null) vd2=parseDate(rget(rows[i],"reg_date")); var w=readWeightG(rows[i]); if(vd2!==null&&w!==null&&w>=WMIN&&w<=WMAX) ws.push([vd2,w]); }
    ws.sort(function(a,b){ return a[0]-b[0]; });
    cases.push({case_id:cid,reg_date:regDate,discharge_date:dischargeDate,dob:dob,birth_location:birthLocation,
      followups:followups,followup_dates:followupDates,n_followup:followups.length,reg_rows:regRows,
      last_visit_date:lastVisitDate,is_death:isDeath,status_entered:statusEntered,conclusion_reason:conclusionReason,is_crf:isCrf,is_early:isEarly,is_exit_exogenous:isExitExogenous,n_additional:nAdditional,weights:ws});
  });
  return cases;
}

// Which of this FLW's opportunities actually ask for `field`? equipment_image and
// kmc_wrap_check exist ONLY in the four V3 apps, but an FLW bucket merges app versions
// (LLO + username), so a PIPN worker spans 524+874+1487. The old "0 populated -> N/A"
// guard ran over the whole merged bucket, so one V3 visit unlocked the metric and then
// every legacy visit counted as a violation (worst: 96.6% RED vs 4.4% true; 33 of 55
// banded FLWs contaminated). Opportunities with zero populated values drop out.
// tagged=false means the rows carry no opportunity_id at all -> callers must not scope.
// PREFER THE GLOBAL MAP (buildFieldOpps over EVERY loaded row). Inferring per-FLW is wrong at
// the edge: a worker who captured ZERO images in their V3 opportunity looks identical to "this
// app has no such question", so they score N/A instead of the 100% RED they earned — that
// silently under-flagged 5 real FLWs. Per-FLW inference is kept only as the no-map fallback.
function fieldOpps(rows, field, globalMap){
  var opps={}, tagged=false, i, o;
  for(i=0;i<rows.length;i++){ o=rget(rows[i],"opportunity_id"); if(o!==null&&o!==undefined){ tagged=true; break; } }
  if(globalMap&&globalMap[field]){ var lst=globalMap[field]; for(i=0;i<lst.length;i++) opps[String(lst[i])]=1; return {opps:opps,tagged:tagged}; }
  for(i=0;i<rows.length;i++){ o=rget(rows[i],"opportunity_id"); if(o===null||o===undefined) continue;
    var fv=rget(rows[i],field); if(fv!==null&&fv!=="") opps[String(o)]=1; }
  return {opps:opps,tagged:tagged};
}
// Global field-presence map: which opportunities' apps actually capture each field. Build once
// over all loaded visit rows and hand it to deriveMetrics.
function buildFieldOpps(rows, fields){
  fields = fields || SCOPED_FIELDS;
  var out={}, i, j, o, seen;
  for(j=0;j<fields.length;j++){
    seen={};
    for(i=0;i<rows.length;i++){ o=rget(rows[i],"opportunity_id");
      if(o===null||o===undefined) continue;
      var fv=rget(rows[i],fields[j]); if(fv!==null&&fv!=="") seen[String(o)]=1; }
    out[fields[j]]=Object.keys(seen).sort();
  }
  return out;
}
function inFieldOpps(row, fo){ return (!fo.tagged) || fo.opps[String(rget(row,"opportunity_id"))]===1; }

function deriveMetrics(aggRow, visitRows, asOf, fieldMap){
  var totalCases=pint(rget(aggRow,"total_cases"))||0;
  var out={}, k, i;
  var cs=groupCases(visitRows);
  var fus=[]; for(i=0;i<cs.length;i++) for(var j=0;j<cs[i].followups.length;j++) fus.push(cs[i].followups[j]);
  function ageDays(regMs){ return (asOf-regMs)/DAY_MS; }

  // 1 low avg visits
  // NOTE: the is_crf exclusion that used to sit here is GONE and must stay gone — it only existed
  // to drop the phantom mother-case. Registrations now key to the baby (caseIdOf), so a case
  // carrying a CRF row IS the baby's case; excluding it would remove nearly every V3 case.
  var elig=cs.filter(function(c){ return c.reg_date!==null && ageDays(c.reg_date)>=60 && !c.is_death && !c.is_exit_exogenous; });
  if(elig.length>=10){ var num=0; for(i=0;i<elig.length;i++) num+=elig[i].n_followup; var avg=num/elig.length; out.low_avg_visits=M(avg,ragLowBad(avg,5,3.0001),num,elig.length); }
  else out.low_avg_visits=NA();

  // 2 mortality
  // register C3 verbatim: numerator = all deaths in cases reg>=28d; denominator = cases reg>=28d
  // WITH a visit after day 28. Counting deaths only inside the pool was survivorship censoring
  // (death stops visits), dropping 61-100% of real deaths -> false RED "under-reporting".
  var reg28=cs.filter(function(c){ return c.reg_date!==null&&ageDays(c.reg_date)>=28; });
  // Denominator = cases mature enough to OBSERVE an outcome: reg>=28d AND (a visit after day 28
  // OR the case died). Including the deaths makes the numerator a subset of the denominator by
  // construction, so >100% is impossible; the register's literal wording leaves them disjoint.
  var pool=reg28.filter(function(c){ if(c.is_death) return true; for(var q=0;q<c.followup_dates.length;q++){ if((c.followup_dates[q]-c.reg_date)/DAY_MS>=28) return true; } return false; });
  if(pool.length>=20){ var deaths=0; for(i=0;i<pool.length;i++) if(pool[i].is_death) deaths++; var rate=100.0*deaths/pool.length; out.mortality=M(rate,ragLowBad(rate,5,3.0001),deaths,pool.length); }
  else out.mortality=NA();

  // 3 enroll ontime
  var hUse=0,hOn=0,mUse=0,mOn=0;
  for(i=0;i<cs.length;i++){ var c=cs[i]; if(c.reg_date===null) continue;
    if(c.birth_location==="hospitalhealth_facility"&&c.discharge_date!==null){ hUse++; if(daysBetween(c.discharge_date,c.reg_date)<=3) hOn++; }
    else if((c.birth_location==="home"||c.birth_location==="other")&&c.dob!==null){ mUse++; if(daysBetween(c.dob,c.reg_date)<=7) mOn++; }
  }
  var _rank={GREEN:0,YELLOW:1,RED:2};
  var hPct=hUse>=10?100.0*hOn/hUse:null, mPct=mUse>=10?100.0*mOn/mUse:null;
  var cohorts=[];
  if(hPct!==null) cohorts.push([ragLowBad(hPct,50,30),hPct,hOn,hUse]);
  if(mPct!==null) cohorts.push([ragLowBad(mPct,50,30),mPct,mOn,mUse]);
  if(cohorts.length){ var worst=cohorts[0]; for(i=1;i<cohorts.length;i++){ var t=cohorts[i]; if(_rank[t[0]]>_rank[worst[0]]||(_rank[t[0]]===_rank[worst[0]]&&t[1]<worst[1])) worst=t; }
    var em=M(worst[1],worst[0],worst[2],worst[3]); em.hosp_pct=hPct; em.home_pct=mPct; out.enroll_ontime=em; }
  else out.enroll_ontime=NA();

  var cwf=cs.filter(function(c){ return c.n_followup>=1; });
  var fuVisitTotal=0; for(i=0;i<cs.length;i++) fuVisitTotal+=cs[i].n_followup;

  // 4 zero danger
  // gate on BOTH populations (register col K = 20 follow-up visits, Definition body = 20 cases)
  if(fuVisitTotal>=20&&cwf.length>=20){ var zero=0; for(i=0;i<cwf.length;i++){ var anyd=false; for(j=0;j<cwf[i].followups.length;j++){ if(low(rget(cwf[i].followups[j],"danger_sign_positive"))==="yes"){ anyd=true; break; } } if(!anyd) zero++; } var pz=100.0*zero/cwf.length; out.zero_danger=M(pz,ragHighBad(pz,50,75),zero,cwf.length); }
  else out.zero_danger=NA();

  // 5 implausible danger (two-sided)
  // both gates again (col K = 30 follow-up visits, Definition body = 10 cases)
  if(fuVisitTotal>=30&&cwf.length>=10){ var anyds=0; for(i=0;i<cwf.length;i++){ var hit=false; for(j=0;j<cwf[i].followups.length;j++){ if(low(rget(cwf[i].followups[j],"danger_sign_positive"))==="yes"){ hit=true; break; } } if(hit) anyds++; } var pd=100.0*anyds/cwf.length; var rg; if(pd<=5||pd>=90) rg="RED"; else if(pd<=10||pd>=60) rg="YELLOW"; else rg="GREEN"; out.danger_rate_cases=M(pd,rg,anyds,cwf.length); }
  else out.danger_rate_cases=NA();

  // 6 no referral after DS
  var dsv=fus.filter(function(v){ return low(rget(v,"danger_sign_positive"))==="yes"; });
  if(dsv.length>=5){ var noref=0; for(i=0;i<dsv.length;i++) if(low(rget(dsv[i],"child_referred"))!=="yes") noref++; var pn=100.0*noref/dsv.length; out.no_referral=M(pn,ragHighBad(pn,30,60),noref,dsv.length); }
  else out.no_referral=NA();

  // weight pairs
  var lossPairs=0,totalPairs=0,gkg=[];
  for(i=0;i<cs.length;i++){ var ws=cs[i].weights; for(var p=1;p<ws.length;p++){ var w1=ws[p-1][1], w2=ws[p][1]; var days=daysBetween(ws[p-1][0],ws[p][0]); if(days<PAIR_MIN||days>PAIR_MAX) continue; totalPairs++; if(w2<w1*0.95) lossPairs++; if(w2>w1&&days>0) gkg.push((w2-w1)/days/(w1/1000.0)); } }
  if(totalPairs>=10){ var pl=100.0*lossPairs/totalPairs; out.weight_loss=M(pl,ragHighBad(pl,5,15),lossPairs,totalPairs); } else out.weight_loss=NA();
  if(gkg.length>=10){ var s=0; for(i=0;i<gkg.length;i++) s+=gkg[i]; var mean=s/gkg.length; out.weight_gain_gkgday=M(mean,ragHighBad(mean,25,40),null,gkg.length); } else out.weight_gain_gkgday=NA();

  // follow-up weights
  var fw=[]; for(i=0;i<fus.length;i++){ var wg=readWeightG(fus[i]); if(wg!==null&&wg>=WMIN&&wg<=WMAX) fw.push(wg); }
  if(fw.length>=20){ var rr=0; for(i=0;i<fw.length;i++) if(rnd(fw[i])%100===0) rr++; var pr=100.0*rr/fw.length; out.rounded_weights=M(pr,ragHighBad(pr,20,60),rr,fw.length); } else out.rounded_weights=NA();
  if(fw.length>=20){ var modal=modalCount(fw.map(function(w){return rnd(w);})); var pm=100.0*modal/fw.length; out.modal_weight=M(pm,ragHighBad(pm,20,35.0001),modal,fw.length); } else out.modal_weight=NA();

  // 11 flat weight
  var c3=cs.filter(function(c){ return c.weights.length>=3; });
  if(c3.length>=20){ var flat=0; for(i=0;i<c3.length;i++){ var wv=c3[i].weights.map(function(t){return t[1];}); var mx=Math.max.apply(null,wv), mn=Math.min.apply(null,wv); if((mx-mn)/wv[0]<=0.02) flat++; } var pfl=100.0*flat/c3.length; out.flat_weight=M(pfl,ragHighBad(pfl,2,5),flat,c3.length); } else out.flat_weight=NA();

  // 12 gps within 200m
  var gcases=0, within=0;
  for(i=0;i<cs.length;i++){ var pts=[]; for(j=0;j<cs[i].followups.length;j++){ var gp=parseGps(rget(cs[i].followups[j],"gps")); if(gp!==null&&(gp[2]===null||gp[2]<=100)) pts.push(gp); } if(pts.length>=2){ gcases++; var dists=[]; for(var a=0;a<pts.length;a++) for(var b=a+1;b<pts.length;b++) dists.push(haversineM(pts[a],pts[b])); if(median(dists)<200) within++; } }
  if(gcases>=20){ var pg=100.0*within/gcases; out.gps_within_200m=M(pg,ragLowBad(pg,50.0001,25),within,gcases); } else out.gps_within_200m=NA();

  // 13/14 hr/temp copycat
  var hrs=[]; for(i=0;i<fus.length;i++){ var hv=pf(rget(fus[i],"heart_rate")); if(hv!==null) hrs.push(hv); }
  if(hrs.length>=10){ var ht=modalCount(hrs); var ph=100.0*ht/hrs.length; out.hr_copycat=M(ph,ragHighBad(ph,20,74.9999),ht,hrs.length); } else out.hr_copycat=NA();
  var temps=[]; for(i=0;i<fus.length;i++){ var tv=pf(rget(fus[i],"temperature")); if(tv!==null) temps.push(tv); }
  if(temps.length>=10){ var tt=modalCount(temps); var pt=100.0*tt/temps.length; out.temp_copycat=M(pt,ragHighBad(pt,50,84.9999),tt,temps.length); } else out.temp_copycat=NA();

  // 15 spo2
  var sp=[]; for(i=0;i<fus.length;i++){ var sv=pf(rget(fus[i],"spo2_level")); if(sv!==null) sp.push(sv); }
  if(sp.length>=20){ var bad=0; for(i=0;i<sp.length;i++) if(sp[i]<70||sp[i]>100) bad++; var ps=100.0*bad/sp.length; out.spo2_implausible=M(ps,ragHighBad(ps,3,5),bad,sp.length); } else out.spo2_implausible=NA();

  // 16 equipment image missing
  var _ifo=fieldOpps(visitRows,"equipment_image",fieldMap);
  // Additional visits are a light check-in form: an image is present on 15.5% of them vs 78.7%
  // of scheduled visits, so including them decided the band for 11 FLWs, 10 of them harmed.
  var fusImg=fus.filter(function(v){ return inFieldOpps(v,_ifo)&&low(rget(v,"visit_type"))!=="additional visit"; });
  if(fusImg.length>=20){ var miss=0,present=0; for(i=0;i<fusImg.length;i++){ var ei=rget(fusImg[i],"equipment_image"); if(ei===null||ei==="") miss++; else present++; } if(present===0&&!_ifo.tagged){ out.image_missing=NA(); } else { var pimg=100.0*miss/fusImg.length; out.image_missing=M(pimg,ragHighBad(pimg,5,20),miss,fusImg.length); } } else out.image_missing=NA();

  // 17 flw early discharge
  // Scope to opportunities whose app actually asks the discharge-reason questions. Opp 675 has ZERO
  // rows carrying either field, so its cases could only ever score 0% — one FLW whose whole
  // denominator came from 675 read 0.0% GREEN on a Priority-1 metric.
  // Direction-aware: absence here yields 0% = the BEST band, so "no data" must never look like
  // "no early discharges". Requires (i) this FLW populated a status field at least once and
  // (ii) the case comes from an opportunity whose app has the field (opp 675 has neither).
  var _sfo=fieldOpps(visitRows,"kmc_status_entered",null), _cfo=fieldOpps(visitRows,"flw_program_conclusion_reason",null);
  var _flwHasStatus=false;
  for(i=0;i<visitRows.length;i++){ if(rget(visitRows[i],"kmc_status_entered")||rget(visitRows[i],"flw_program_conclusion_reason")){ _flwHasStatus=true; break; } }
  function _statusCapable(c){
    if(!_sfo.tagged&&!_cfo.tagged) return true;
    var rr=c.followups.concat(c.reg_rows), q;
    for(q=0;q<rr.length;q++){ var o=String(rget(rr[q],"opportunity_id")); if(_sfo.opps[o]===1||_cfo.opps[o]===1) return true; }
    return false;
  }
  var e60=_flwHasStatus?cs.filter(function(c){ return c.reg_date!==null&&ageDays(c.reg_date)>=60&&_statusCapable(c); }):[];
  if(e60.length>=10){ var early=0; for(i=0;i<e60.length;i++){ if(e60[i].is_early) early++; } var ped=100.0*early/e60.length; out.flw_early_discharge=M(ped,ragHighBad(ped,5,15),early,e60.length); } else out.flw_early_discharge=NA();

  // 18 kmc wrap missing at reg
  var _wfo=fieldOpps(visitRows,"kmc_wrap_check",fieldMap);
  var regCases=cs.filter(function(c){ if(c.reg_rows.length===0) return false; for(var q=0;q<c.reg_rows.length;q++){ if(inFieldOpps(c.reg_rows[q],_wfo)) return true; } return false; });
  if(regCases.length>=20){ var bd=0,presentW=0; for(i=0;i<regCases.length;i++){ var wrap=null; for(j=0;j<regCases[i].reg_rows.length;j++){ var wv=low(rget(regCases[i].reg_rows[j],"kmc_wrap_check")); if(wv!==null){ wrap=wv; break; } } if(wrap!==null) presentW++; if(wrap!=="yes") bd++; } if(presentW===0&&!_wfo.tagged){ out.kmc_wrap_missing=NA(); } else { var pw=100.0*bd/regCases.length; out.kmc_wrap_missing=M(pw,ragHighBad(pw,15,40),bd,regCases.length); } } else out.kmc_wrap_missing=NA();

  // Retained for the UI as a LABEL, not a gate — every metric above enforced its own register minimum.
  out._excluded=false; out._low_caseload=totalCases<LOW_CASELOAD_CASES; out._total_cases=totalCases;
  return out;
}

// ============================= display metadata =============================
var OPP_META = {523:{llo:"NAMA",ver:"V1",name:"NAMA (V0/V1)"},524:{llo:"PIPN",ver:"V1",name:"PIPN (V0/V1)"},675:{llo:"GHI",ver:"V1",name:"GHI-KE (V0/V1)"},874:{llo:"PIPN",ver:"V2",name:"PIPN (V2)"},938:{llo:"NAMA",ver:"V2",name:"NAMA (V2)"},1487:{llo:"PIPN",ver:"V3",name:"PIPN (V3)"},1488:{llo:"NAMA",ver:"V3",name:"NAMA (V3)"},1234:{llo:"GHI",ver:"V2",name:"GHI-KE (V2)"},1739:{llo:"Kikapu",ver:"V3",name:"Kikapu (V3)"},1236:{llo:"EHA",ver:"V2",name:"EHA (V2+)"},1790:{llo:"BERI",ver:"V3",name:"BERI (V3)"}};
function verFor(oppId){ var m=OPP_META[oppId]; return m?m.ver:"?"; }
var COUNTRY = {523:"Uganda",524:"Uganda",675:"Kenya",874:"Uganda",938:"Uganda",1487:"Uganda",1488:"Uganda",1234:"Kenya",1739:"Kenya",1236:"Nigeria",1790:"Nigeria"};
function countryFor(oppId){ return COUNTRY[oppId]||"Other"; }
var P1_ORDER = ["low_avg_visits","mortality","enroll_ontime","zero_danger","no_referral","rounded_weights","gps_within_200m","hr_copycat","temp_copycat","spo2_implausible","flw_early_discharge"];
var P2_ORDER = ["danger_rate_cases","weight_loss","weight_gain_gkgday","modal_weight","flat_weight","image_missing","kmc_wrap_missing"];
var META = {
  low_avg_visits:{label:"Visits/case",unit:"dec",bands:"G>=5  Y 3-5  R<=3",desc:"Avg follow-up visits per case enrolled >=60 days ago. Excludes deaths and cases that exited early (those are scored on Early discharge instead, so one event is not penalised twice). Successful graduations DO count. Min 10 cases."},
  mortality:{label:"Mortality",unit:"pct",bands:"R<=3%  Y 3-5%  G>=5%",desc:"Deaths over cases reg>=28d that were observable: a visit after day 28 OR the case died. LOW = under-reporting concern. Min 20 cases."},
  enroll_ontime:{label:"Enroll on-time",unit:"pct",bands:"G>=50  Y 30-49  R<30",desc:"% enrolled on time: hospital reg<=discharge+3d; home reg<=DOB+7d. Min 10 cases."},
  zero_danger:{label:"Zero danger",unit:"pct",bands:"G<50  Y 50-75  R>75",desc:"% cases with NO danger sign ever recorded. Min 20 follow-up visits AND 20 visited cases."},
  no_referral:{label:"No referral",unit:"pct",bands:"G<30  Y 30-60  R>60",desc:"% danger-sign-positive visits with no referral. Min 5 DS+ visits."},
  rounded_weights:{label:"Rounded wt",unit:"pct",bands:"G<20  Y 20-60  R>60",desc:"% follow-up weights that are exact 100g multiples. Analog 100g dial scales round by construction. Min 20 weights."},
  gps_within_200m:{label:"GPS <200m",unit:"pct",bands:"G>50  Y 25-50  R<25",desc:"% cases whose same-case follow-up GPS points are within a 200m median. Higher is better. Min 20 cases."},
  hr_copycat:{label:"HR copycat",unit:"pct",bands:"G<20  Y 20-74  R>=75",desc:"% of heart-rate readings that are the single modal value. Min 10 readings."},
  temp_copycat:{label:"Temp copycat",unit:"pct",bands:"G<50  Y 50-84  R>=85",desc:"% of temperature readings that are the single modal value. Min 10 readings."},
  spo2_implausible:{label:"SpO2 impl.",unit:"pct",bands:"G<3  Y 3-5  R>5",desc:"% SpO2 readings outside 70-100. Min 20 readings."},
  flw_early_discharge:{label:"Early discharge",unit:"pct",bands:"G<5  Y 5-15  R>15",desc:"% cases reg>=60d discharged for parent-discontinued / caregiver-unavailable / family-relocated, or clinically discharged before visit 4. Min 10 cases."},
  danger_rate_cases:{label:"Danger rate",unit:"pct",bands:"G 10-60  Y 5-10 or 60-89  R 0-5 or 90-100",desc:"% cases with any danger sign. Two-sided: implausibly low OR high. Min 30 follow-up visits AND 10 visited cases."},
  weight_loss:{label:"Weight loss",unit:"pct",bands:"G<5  Y 5-15  R>15",desc:"% consecutive weight pairs with a >5% drop. Min 10 pairs."},
  weight_gain_gkgday:{label:"Weight gain",unit:"gkg",bands:"G<25  Y 25-40  R>40",desc:"Avg daily weight gain (g/kg/day) over increasing pairs. Min 10 pairs."},
  modal_weight:{label:"Modal wt",unit:"pct",bands:"G<20  Y 20-35  R>35",desc:"% of weights that are the single most-frequent value (across cases). Min 20 weights."},
  flat_weight:{label:"Flat wt",unit:"pct",bands:"G<2  Y 2-5  R>5",desc:"% cases (>=3 weights) whose weight range is <=2% of the first weight. Min 20 cases."},
  image_missing:{label:"Equip image",unit:"pct",bands:"G<5  Y 5-20  R>20",desc:"% follow-up visits with no equipment image captured. Counts only visits from opportunities whose app asks for it (V3). N/A where the app lacks the field. Min 20 such visits."},
  kmc_wrap_missing:{label:"KMC wrap",unit:"pct",bands:"G<15  Y 15-40  R>40",desc:"% cases where the KMC wrap was not provided at registration. Counts only cases from opportunities whose app asks for it (V3). N/A where the app lacks the field. Min 20 such cases."}
};

// register "Tier / Category" grouping — tells a program head WHAT KIND of problem a red is.
var CAT = {
  mortality:"Fraud / data integrity", modal_weight:"Fraud / data integrity",
  flat_weight:"Fraud / data integrity", gps_within_200m:"Fraud / data integrity", hr_copycat:"Fraud / data integrity",
  temp_copycat:"Fraud / data integrity", spo2_implausible:"Fraud / data integrity",
  zero_danger:"Clinical quality & skill", danger_rate_cases:"Clinical quality & skill", no_referral:"Clinical quality & skill",
  weight_loss:"Clinical quality & skill", weight_gain_gkgday:"Clinical quality & skill", image_missing:"Clinical quality & skill",
  kmc_wrap_missing:"Clinical quality & skill",
  // register row 10 puts rounded weights under Clinical Quality & Skill ("Possible - estimation",
  // "Yes - measurement technique"), NOT fraud: 100g analog dial scales (EHA/BERI Salter, NAMA KINLee)
  // round by construction, so filing it as fabrication mislabels whole LLOs.
  rounded_weights:"Clinical quality & skill",
  low_avg_visits:"Model adherence", enroll_ontime:"Model adherence", flw_early_discharge:"Model adherence"
};
var CAT_ORDER = ["Fraud / data integrity","Clinical quality & skill","Model adherence"];
var CAT_DESC = {"Fraud / data integrity":"Fabricated / copy-pasted data (weights, vitals, GPS) or implausibly low mortality.",
  "Clinical quality & skill":"Danger-sign detection, referrals, weight trends, equipment & wrap compliance.",
  "Model adherence":"Visit frequency, timely enrollment, FLW-driven early discharge."};

// Metrics that legitimately re-scope to a date window (they judge the READINGS TAKEN in the period).
// The other 12 are cohort/outcome metrics that need each case's full history (visits/case, mortality,
// enrollment timing, weight trends, danger detection, early discharge) and are NEVER windowed.
var WINDOWED_METRICS = {rounded_weights:1, modal_weight:1, hr_copycat:1, temp_copycat:1, spo2_implausible:1, gps_within_200m:1};
var WINDOWED_METRICS_LIST = ["rounded_weights","modal_weight","hr_copycat","temp_copycat","spo2_implausible","gps_within_200m"];

function fmtVal(v, unit){ if(v===null||v===undefined) return null; if(unit==="pct") return v.toFixed(1)+"%"; if(unit==="dec") return v.toFixed(1); if(unit==="gkg") return v.toFixed(1); return String(v); }
function fmtSub(m){ if(m.hosp_pct!==undefined||m.home_pct!==undefined){ var parts=[]; if(m.hosp_pct!==null&&m.hosp_pct!==undefined) parts.push("Hosp "+m.hosp_pct.toFixed(0)+"%"); if(m.home_pct!==null&&m.home_pct!==undefined) parts.push("Home "+m.home_pct.toFixed(0)+"%"); if(parts.length) return parts.join(" · "); } if(m.den===null||m.den===undefined) return null; if(m.num===null||m.num===undefined) return "n="+m.den; return m.num+" / "+m.den; }

function lloFor(oppId){ var m=OPP_META[oppId]; return m?m.llo:("opp_"+oppId); }
// ---- V3 case-count correction (mirrors Superset KMC_Cases_Optimized; UI-only, not the parity core) ----
// A 'Child Registration Form' row's beneficiary_case_id can only have come from case.@case_id (V3 CRF rows
// carry no child_case_id/kmc_beneficiary_case_id), so guarding that form = Superset's "V3 dual-case fix".
// Registrations now resolve to the CHILD via caseIdOf (form.subcase_0.case.@case_id), so a V3
// registration no longer has to be discarded to avoid the mother-case double count — it names a
// real baby. This also counts babies registered but not yet visited, which the old rule dropped.
function correctedCaseId(row){ return caseIdOf(row); }
function correctedCaseCount(rows, opp){
  var s={}, i, cc, fn, elig;
  for(i=0;i<rows.length;i++){
    cc=correctedCaseId(rows[i]); if(!cc) continue;
    fn=low(rget(rows[i],"form_name"));
    // Superset eligibility filter: count a 'Register KMC Beneficiary' reg only if eligible (or opp 675).
    elig=(fn!=="register kmc beneficiary")||(low(rget(rows[i],"eligibility_status"))==="eligible")||(String(rows[i].opportunity_id||opp)==="675");
    if(elig) s[String(cc)]=1;
  }
  return Object.keys(s).length;
}

function buildMasterRows(flwRows, visitRows, nameByUser, asOf, winStartMs, winEndMs){
  nameByUser=nameByUser||{};
  var winActive = (winStartMs!==null && winStartMs!==undefined && winEndMs!==null && winEndMs!==undefined);
  // ONE field-presence map over EVERY loaded visit row, handed to every FLW. Built globally on
  // purpose: per-FLW inference cannot tell "this app has no equipment-image question" from
  // "this worker never took one", which silently excused 5 FLWs from a 100% RED.
  var fieldMap = buildFieldOpps(visitRows);
  var visitsByOppUser={}, i, r, k;
  for(i=0;i<visitRows.length;i++){ r=visitRows[i]; k=r.opportunity_id+"|"+r.username; (visitsByOppUser[k]=visitsByOppUser[k]||[]).push(r); }
  var buckets={};
  var sorted=flwRows.slice().sort(function(a,b){return (a.opportunity_id||0)-(b.opportunity_id||0);});
  for(i=0;i<sorted.length;i++){ r=sorted[i]; var uname=r.username; if(!uname) continue; var llo=lloFor(r.opportunity_id); var bkey=llo+"|"+uname;
    var b=buckets[bkey]; if(!b){ b=buckets[bkey]={username:uname,llo:llo,flw_name:null,agg_total_cases:0,visit_rows:[],opportunity_ids:[],opportunity_breakdown:[]}; }
    if(!b.flw_name) b.flw_name=nameByUser[uname]||r.flw_name||null;
    var vs=visitsByOppUser[r.opportunity_id+"|"+uname]||[]; for(var j=0;j<vs.length;j++) b.visit_rows.push(vs[j]);
    // total_cases = distinct corrected+eligible case-ids (fixes the V3 double-count; aggregated pipeline value ignored)
    var oc=correctedCaseCount(vs, r.opportunity_id), ov=parseInt(r.kmc_visit_count,10)||0;
    b.agg_total_cases+=oc;
    b.opportunity_ids.push(r.opportunity_id);
    b.opportunity_breakdown.push({opportunity_id:r.opportunity_id,name:(OPP_META[r.opportunity_id]||{}).name||("Opp "+r.opportunity_id),total_cases:oc,kmc_visit_count:ov});
  }
  var out=[];
  Object.keys(buckets).forEach(function(bk){ var b=buckets[bk];
    var aggDict={username:b.username,total_cases:b.agg_total_cases};
    var res=deriveMetrics(aggDict,b.visit_rows,asOf,fieldMap);
    res.username=b.username; res.flw_name=b.flw_name||b.username; res.llo=b.llo;
    res.opportunity_ids=b.opportunity_ids.slice(); res.opportunity_breakdown=b.opportunity_breakdown.slice();
    res.versions=[]; for(var vi=0;vi<b.opportunity_ids.length;vi++){ var vv=verFor(b.opportunity_ids[vi]); if(res.versions.indexOf(vv)<0) res.versions.push(vv); }
    res.primary_opp=b.opportunity_ids.length?Math.max.apply(null,b.opportunity_ids):null;
    res.country=countryFor(res.primary_opp);
    res._visit_rows=b.visit_rows; res.total_cases=b.agg_total_cases;
    // Visit counts, shown as a scheduled / additional breakdown. An "Additional Visit" carries the
    // string "Additional" in visit_number, which the pipeline's int transform nulls — so it must be
    // recognised by visit_type or 481 real visits go uncounted. Deduped the same way the engine
    // dedupes, so the displayed total matches the metric denominators instead of over-reporting.
    var _seenV={}, _sch=0, _add=0;
    for(var _q=0;_q<b.visit_rows.length;_q++){
      var _v=b.visit_rows[_q], _vn=pint(rget(_v,"visit_number"));
      var _isA=low(rget(_v,"visit_type"))==="additional visit";
      if(_vn===null&&!_isA) continue;
      if(parseDate(rget(_v,"visit_date"))===null) continue;
      var _kk=String(rget(_v,"beneficiary_case_id"))+"|"+((_vn!==null)?("N:"+_vn):("A:"+rget(_v,"visit_date")));
      if(_seenV[_kk]) continue;
      _seenV[_kk]=1;
      if(_isA) _add++; else _sch++;
    }
    res.total_visits=_sch+_add; res.scheduled_visits=_sch; res.additional_visits=_add;
    // ---- windowed variant (display only): re-run the SAME deriveMetrics on window-filtered visits.
    // Full-history total_cases stays in aggDict so the <20-case exclusion remains a lifetime decision.
    var winVisits=b.visit_rows;
    if(winActive){ winVisits=b.visit_rows.filter(function(v){ var vd=parseDate(rget(v,"visit_date")); return vd!==null && vd>=winStartMs && vd<=winEndMs; }); }
    res._win_visits=winVisits.length;
    res.in_window = winActive ? (winVisits.length>0) : true;
    var resWin = winActive ? deriveMetrics(aggDict, winVisits, asOf, fieldMap) : res;
    res.win={}; for(var wi=0;wi<WINDOWED_METRICS_LIST.length;wi++){ var wk=WINDOWED_METRICS_LIST[wi]; res.win[wk]=resWin[wk]; }
    // ---- effective bands = windowed for the 6 windowable metrics (when a window is set) + full-history for the rest
    var red=0,yellow=0,p1red=0;
    for(var mi=0;mi<METRIC_KEYS.length;mi++){ var mk=METRIC_KEYS[mi];
      var bnd=(winActive && WINDOWED_METRICS[mk]) ? (res.win[mk]?res.win[mk].rag:"N/A") : res[mk].rag;
      if(bnd==="RED"){ red++; if(PRIORITY[mk]===1) p1red++; } else if(bnd==="YELLOW") yellow++; }
    res.red_count=red; res.yellow_count=yellow; res.p1_red_count=p1red;
    out.push(res);
  });
  return out;
}

// ============================= UI =============================
function WorkflowUI({ definition, instance, workers, pipelines, links, actions, onUpdateState }) {
  var h = React.createElement;
  var flwRows = (pipelines && pipelines.flw_flags && pipelines.flw_flags.rows) || [];
  var visitRows = (pipelines && pipelines.weight_series && pipelines.weight_series.rows) || [];
  var asOf = React.useMemo(function(){ return Date.now(); }, []);
  var nameByUser = React.useMemo(function(){ var m={}; (workers||[]).forEach(function(w){ if (w && w.username && w.name) m[w.username]=w.name; }); return m; }, [workers]);
  // ---- date window (opt-in; default "all time" == today's behaviour) ----
  var _winP = React.useState("all"); var winPreset=_winP[0], setWinPreset=_winP[1];
  var _winS = React.useState(""); var winStart=_winS[0], setWinStart=_winS[1];
  var _winE = React.useState(""); var winEnd=_winE[0], setWinEnd=_winE[1];
  var winActive = !!(winStart && winEnd);
  var winStartMs = winActive ? parseDate(winStart) : null;
  var winEndMs = winActive ? parseDate(winEnd) : null;
  var masterRows = React.useMemo(function(){ return buildMasterRows(flwRows, visitRows, nameByUser, asOf, winStartMs, winEndMs); }, [flwRows, visitRows, nameByUser, asOf, winStartMs, winEndMs]);
  var scoped = React.useMemo(function(){ return winActive ? masterRows.filter(function(r){return r.in_window;}) : masterRows; }, [masterRows, winActive]);
  function effM(r,k){ return (winActive && WINDOWED_METRICS[k] && r.win && r.win[k]) ? r.win[k] : r[k]; }
  function effRag(r,k){ var m=effM(r,k); return m?m.rag:"N/A"; }
  function computeWindow(preset){
    var now=new Date(); var fmt=function(d){return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");};
    var s=new Date(now);
    if(preset==="last_week"){ s.setDate(now.getDate()-7); return {start:fmt(s),end:fmt(now)}; }
    if(preset==="last_2_weeks"){ s.setDate(now.getDate()-14); return {start:fmt(s),end:fmt(now)}; }
    if(preset==="last_month"){ s.setDate(now.getDate()-30); return {start:fmt(s),end:fmt(now)}; }
    return {start:"",end:""};
  }
  function applyPreset(p){ setWinPreset(p); if(p!=="custom"){ var w=computeWindow(p); setWinStart(w.start); setWinEnd(w.end); } }

  var _tab = React.useState("overview"); var activeTab=_tab[0], setActiveTab=_tab[1];
  // Per-indicator slice: a list of {k: metric, b: band} conditions. condMode decides whether an
  // FLW has to satisfy all of them or any one of them, so you can ask both "red on early discharge
  // AND red on zero danger" (a repeat offender) and "red on either" (the union to chase).
  var _mc = React.useState([]); var metricConds=_mc[0], setMetricConds=_mc[1];
  var _mm = React.useState("all"); var condMode=_mm[0], setCondMode=_mm[1];
  function condMatch(d,c){ var rg=effRag(d,c.k); if(c.b==="flag") return rg==="RED"||rg==="YELLOW"; if(c.b==="any") return true; return rg===c.b; }
  function condsPass(d,cs){ if(!cs.length) return true; var n=0; for(var ci=0;ci<cs.length;ci++){ if(condMatch(d,cs[ci])) n++; } return condMode==="any" ? n>0 : n===cs.length; }
  // Adding or focusing an indicator also sorts by it, worst first — otherwise the column you just
  // asked about comes back in red-count order and reads as noise.
  function addCond(k){ for(var ci=0;ci<metricConds.length;ci++){ if(metricConds[ci].k===k) return; } setMetricConds(metricConds.concat([{k:k,b:"RED"}])); setSortKey(k); setSortAsc(false); }
  function setCondBand(i,b){ var n=metricConds.slice(); n[i]={k:n[i].k,b:b}; setMetricConds(n); setSortKey(n[i].k); setSortAsc(false); }
  function removeCond(i){ var n=metricConds.slice(); n.splice(i,1); setMetricConds(n); }
  // Jump from the Overview scoreboard straight into the filtered FLW list.
  function focusMetric(k, band){ setMetricConds([{k:k,b:band}]); setCondMode("all"); setSortKey(k); setSortAsc(false); setActiveTab("detail"); }
  function bandWord(b){ return b==="flag" ? "Red or Yellow" : b==="any" ? "any band" : b==="N/A" ? "not eligible" : b.charAt(0)+b.slice(1).toLowerCase(); }
  var byLloRef = React.useRef(null), byLloInst = React.useRef(null);
  var topFlagRef = React.useRef(null), topFlagInst = React.useRef(null);

  var _filter = React.useState("any_red"); var filter=_filter[0], setFilter=_filter[1];
  var _llo = React.useState("all"); var lloFilter=_llo[0], setLloFilter=_llo[1];
  var _ver = React.useState("all"); var verFilter=_ver[0], setVerFilter=_ver[1];
  // Version slice: when a specific app version is picked, rebuild each FLW's
  // metrics from ONLY that version's opportunity rows/visits (mirrors the date-
  // window re-derivation) so flag counts reflect the version, not the all-version
  // merge. No-op when "all". Reassigns `scoped` so cards + Overview + table agree.
  var vScoped = React.useMemo(function(){
    if (verFilter === "all") return scoped;
    var _fR = flwRows.filter(function(r){ return verFor(r.opportunity_id) === verFilter; });
    var _vR = visitRows.filter(function(v){ return verFor(v.opportunity_id) === verFilter; });
    var _mr = buildMasterRows(_fR, _vR, nameByUser, asOf, winStartMs, winEndMs);
    return winActive ? _mr.filter(function(r){ return r.in_window; }) : _mr;
  }, [scoped, flwRows, visitRows, nameByUser, asOf, winStartMs, winEndMs, winActive, verFilter]);
  scoped = vScoped;
  var _search = React.useState(""); var search=_search[0], setSearch=_search[1];
  var _sortKey = React.useState("red"); var sortKey=_sortKey[0], setSortKey=_sortKey[1];
  var _sortAsc = React.useState(false); var sortAsc=_sortAsc[0], setSortAsc=_sortAsc[1];
  var _showP2 = React.useState(false); var showP2=_showP2[0], setShowP2=_showP2[1];
  var _expScope = React.useState("view"); var exportScope=_expScope[0], setExportScope=_expScope[1];
  var _copied = React.useState(""); var copiedMsg=_copied[0], setCopiedMsg=_copied[1];
  var _expanded = React.useState(null); var expanded=_expanded[0], setExpanded=_expanded[1];
  var _sel = React.useState({}); var selected=_sel[0], setSelected=_sel[1];
  var _modal = React.useState(false); var showModal=_modal[0], setShowModal=_modal[1];
  var _running = React.useState(false); var isRunning=_running[0], setIsRunning=_running[1];
  var _progress = React.useState(null); var progress=_progress[0], setProgress=_progress[1];
  var _start = React.useState(""); var startDate=_start[0], setStartDate=_start[1];
  var _end = React.useState(""); var endDate=_end[0], setEndDate=_end[1];
  var _count = React.useState(10); var countPerFlw=_count[0], setCountPerFlw=_count[1];
  var _ai = React.useState("scale_validation"); var aiAgent=_ai[0], setAiAgent=_ai[1];

  React.useEffect(function(){ if (!startDate){ var now=new Date(); var fmt=function(d){return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");}; var start=new Date(now); start.setDate(now.getDate()-14); setStartDate(fmt(start)); setEndDate(fmt(now)); } }, []);

  var kpi = React.useMemo(function(){
    var loaded=scoped.length, excluded=0, anyRed=0, anyYellow=0, totalVisits=0, totalCases=0, addVisits=0;
    scoped.forEach(function(r){ if (r._low_caseload) excluded++; if (r.red_count>=1) anyRed++; if (r.yellow_count>=1) anyYellow++; totalVisits+=r.total_visits||0; totalCases+=r.total_cases||0; addVisits+=r.additional_visits||0; });
    return { loaded:loaded, excluded:excluded, anyRed:anyRed, anyYellow:anyYellow, totalVisits:totalVisits, totalCases:totalCases, addVisits:addVisits };
  }, [scoped]);

  var freshness = React.useMemo(function(){
    var latest=null;
    for (var i=0;i<visitRows.length;i++){ var d=parseDate(visitRows[i].visit_date); if (d!==null && (latest===null || d>latest)) latest=d; }
    function fmtDT(ms){ return new Date(ms).toLocaleString(undefined,{year:"numeric",month:"short",day:"numeric",hour:"2-digit",minute:"2-digit"}); }
    function fmtD(ms){ return new Date(ms).toLocaleDateString(undefined,{year:"numeric",month:"short",day:"numeric"}); }
    return { loaded:fmtDT(asOf), latestVisit:(latest!==null?fmtD(latest):null) };
  }, [visitRows, asOf]);

  var overview = React.useMemo(function(){
    var byC={}, lloTotals={};
    scoped.forEach(function(r){
      var c=r.country||"Other", l=r.llo;
      byC[c]=byC[c]||{}; var s=byC[c][l]=byC[c][l]||{flws:0,red:0,yellow:0,clean:0,excluded:0};
      var t=lloTotals[l]=lloTotals[l]||{red:0,yellow:0,clean:0,excluded:0};
      s.flws++;
      if (r._low_caseload){ s.excluded++; t.excluded++; }
      else if (r.red_count>=1){ s.red++; t.red++; }
      else if (r.yellow_count>=1){ s.yellow++; t.yellow++; }
      else { s.clean++; t.clean++; }
    });
    var flagRed={}; for (var mi=0;mi<METRIC_KEYS.length;mi++) flagRed[METRIC_KEYS[mi]]=0;
    scoped.forEach(function(r){ for (var mj=0;mj<METRIC_KEYS.length;mj++){ var k=METRIC_KEYS[mj]; if (effRag(r,k)==="RED") flagRed[k]++; } });
    var topFlags=METRIC_KEYS.map(function(k){ return {k:k,label:META[k].label,red:flagRed[k]}; }).sort(function(a,b){ return b.red-a.red; });
    var catRed={}; for (var ci=0;ci<CAT_ORDER.length;ci++) catRed[CAT_ORDER[ci]]=0;
    var risk=[], analyzedN=0, flaggedRedN=0, cleanN=0;
    scoped.forEach(function(r){
      // low-caseload FLWs are scored now, so they belong in the risk list if they carry flags
      analyzedN++;
      var catHit={}, reds=[];
      for (var mi=0;mi<METRIC_KEYS.length;mi++){ var k=METRIC_KEYS[mi]; if (effRag(r,k)==="RED"){ reds.push(META[k].label); catHit[CAT[k]]=1; } }
      for (var cj=0;cj<CAT_ORDER.length;cj++){ if (catHit[CAT_ORDER[cj]]) catRed[CAT_ORDER[cj]]++; }
      if (r.red_count>=1) { flaggedRedN++; risk.push({name:r.flw_name||r.username, username:r.username, llo:r.llo, country:r.country, cases:r.total_cases, red:r.red_count, yellow:r.yellow_count, flags:reds}); }
      else if (r.yellow_count<1) cleanN++;
    });
    risk.sort(function(a,b){ return (b.red-a.red)||(b.cases-a.cases); });
    return { byC:byC, lloTotals:lloTotals, topFlags:topFlags, catRed:catRed, risk:risk, analyzedN:analyzedN, flaggedRedN:flaggedRedN, cleanN:cleanN };
  }, [scoped, winActive]);

  React.useEffect(function(){
    if (activeTab!=="overview" || !byLloRef.current || !window.Chart) return;
    if (byLloInst.current) byLloInst.current.destroy();
    var llos=Object.keys(overview.lloTotals);
    byLloInst.current=new window.Chart(byLloRef.current.getContext("2d"),{type:"bar",data:{labels:llos,datasets:[
      {label:"Red",data:llos.map(function(l){return overview.lloTotals[l].red;}),backgroundColor:"#ef4444"},
      {label:"Yellow",data:llos.map(function(l){return overview.lloTotals[l].yellow;}),backgroundColor:"#f59e0b"},
      {label:"Clean",data:llos.map(function(l){return overview.lloTotals[l].clean;}),backgroundColor:"#22c55e"},
      {label:"Low caseload",data:llos.map(function(l){return overview.lloTotals[l].excluded;}),backgroundColor:"#d1d5db"}]},
      options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:"bottom",labels:{font:{size:10}}}},scales:{x:{stacked:true,ticks:{font:{size:10}}},y:{stacked:true,beginAtZero:true,ticks:{font:{size:10}}}}}});
    return function(){ if (byLloInst.current){ byLloInst.current.destroy(); byLloInst.current=null; } };
  }, [activeTab, overview]);

  React.useEffect(function(){
    if (activeTab!=="overview" || !topFlagRef.current || !window.Chart) return;
    if (topFlagInst.current) topFlagInst.current.destroy();
    var tf=overview.topFlags.slice(0,10);
    topFlagInst.current=new window.Chart(topFlagRef.current.getContext("2d"),{type:"bar",data:{labels:tf.map(function(x){return x.label;}),datasets:[{label:"FLWs flagged RED",data:tf.map(function(x){return x.red;}),backgroundColor:"#ef4444"}]},
      options:{indexAxis:"y",responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{beginAtZero:true,ticks:{font:{size:10}}},y:{ticks:{font:{size:10}}}}}});
    return function(){ if (topFlagInst.current){ topFlagInst.current.destroy(); topFlagInst.current=null; } };
  }, [activeTab, overview]);

  var analyzed = scoped;
  // Everything the FLW Detail tab filters on EXCEPT the per-indicator conditions. The table AND the
  // indicator chips both derive from this single memo. Computing the two chains separately is
  // exactly how the chips came to report one cohort while the rows they filter to were another —
  // the invariant "chip count == rows you get by clicking it" has to hold by construction, not by
  // two copies of the same five filters staying in step.
  var baseFiltered = React.useMemo(function(){
    var data = analyzed.slice();
    if (lloFilter!=="all") data=data.filter(function(d){return d.llo===lloFilter;});
    if (verFilter!=="all") data=data.filter(function(d){return d.versions.indexOf(verFilter)>=0;});
    if (search.trim()){ var q=search.toLowerCase(); data=data.filter(function(d){ return (d.username&&d.username.toLowerCase().indexOf(q)>=0)||(d.flw_name&&d.flw_name.toLowerCase().indexOf(q)>=0); }); }
    if (filter==="any_red") data=data.filter(function(d){return d.red_count>=1;});
    else if (filter==="two_red") data=data.filter(function(d){return d.red_count>=2;});
    else if (filter==="any_yellow") data=data.filter(function(d){return d.yellow_count>=1;});
    return data;
  }, [analyzed, filter, lloFilter, verFilter, search, winActive]);

  var filtered = React.useMemo(function(){
    var data = baseFiltered.slice();
    // Per-indicator slice. This is what makes "how many FLWs are RED on early discharge"
    // answerable — the footer count and the Export toolbar both follow it, so the number can be
    // read or exported directly.
    if (metricConds.length) data=data.filter(function(d){ return condsPass(d, metricConds); });
    data.sort(function(a,b){
      var va, vb;
      if (sortKey==="name"){ va=a.flw_name||a.username||""; vb=b.flw_name||b.username||""; var c=va.localeCompare(vb); return sortAsc?c:-c; }
      if (sortKey==="cases"){ va=a.total_cases; vb=b.total_cases; }
      else if (sortKey==="red"){ va=a.red_count*100+a.yellow_count; vb=b.red_count*100+b.yellow_count; }
      else { var ma=effM(a,sortKey), mb=effM(b,sortKey); va=(ma&&ma.value!=null?ma.value:-1); vb=(mb&&mb.value!=null?mb.value:-1); }
      return sortAsc?va-vb:vb-va;
    });
    return data;
  }, [baseFiltered, sortKey, sortAsc, metricConds, condMode]);

  function bandTally(pool, kk){
    var t={GREEN:0,YELLOW:0,RED:0,"N/A":0};
    for (var bi=0;bi<pool.length;bi++){ var rg=effRag(pool[bi],kk); if(t[rg]!==undefined) t[rg]++; }
    return t;
  }

  // Overview scoreboard tally: every indicator over the LLO/version/window scope only. Deliberately
  // blind to the FLW Detail tab's own filters — the scoreboard is meant to report the whole cohort.
  var metricTally = React.useMemo(function(){
    var base=analyzed.slice();
    if (lloFilter!=="all") base=base.filter(function(d){return d.llo===lloFilter;});
    if (verFilter!=="all") base=base.filter(function(d){return d.versions.indexOf(verFilter)>=0;});
    var out={};
    for (var mi=0;mi<METRIC_KEYS.length;mi++){ out[METRIC_KEYS[mi]]=bandTally(base, METRIC_KEYS[mi]); }
    return out;
  }, [analyzed, lloFilter, verFilter, winActive]);

  // Detail-tab chip tally: the SAME baseFiltered the table uses, minus the condition on the metric
  // being tallied. With one condition active `others` is empty, so pool === baseFiltered and the
  // chip is literally the row count clicking it produces.
  var metricTallyView = React.useMemo(function(){
    var out={};
    for (var mi=0;mi<METRIC_KEYS.length;mi++){
      var kk=METRIC_KEYS[mi], others=[];
      for (var ci=0;ci<metricConds.length;ci++){ if (metricConds[ci].k!==kk) others.push(metricConds[ci]); }
      // In ANY mode the other conditions add rows rather than remove them, so a "rest of the
      // conditions" pre-filter would understate the chip. Tally the plain base there.
      var pool = (condMode==="any" || !others.length) ? baseFiltered : baseFiltered.filter(function(d){ return condsPass(d, others); });
      out[kk]=bandTally(pool, kk);
    }
    return out;
  }, [baseFiltered, metricConds, condMode]);

  var selectedRows = filtered.filter(function(d){ return selected[d.llo+"|"+d.username]; });
  var selectedCount = selectedRows.length;
  function toggleSort(kk){ if (sortKey===kk) setSortAsc(!sortAsc); else { setSortKey(kk); setSortAsc(false); } }
  function rowKey(d){ return d.llo+"|"+d.username; }
  function toggleSelect(d){ setSelected(function(prev){ var n=Object.assign({},prev); var kk=rowKey(d); n[kk]=!prev[kk]; return n; }); }
  function SortArrow(kk){ if (sortKey!==kk) return null; return h("span",{className:"ml-1 text-xs"}, sortAsc?"▲":"▼"); }
  var thBase="px-2 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none whitespace-nowrap";

  function bandColor(band){ return band==="RED"?"bg-red-50 text-red-800 font-semibold":band==="YELLOW"?"bg-amber-50 text-amber-800 font-medium":band==="GREEN"?"bg-green-50 text-green-700":"text-gray-400"; }
  function metricCell(d, key){
    var meta=META[key]; var windowed=winActive && WINDOWED_METRICS[key];
    var m=windowed ? (d.win[key]||d[key]) : d[key];
    var band=m.rag; var val=fmtVal(m.value, meta.unit); var sub=fmtSub(m);
    var cls="px-2 py-2 text-center whitespace-nowrap ";
    var tag=windowed ? h("span",{className:"ml-0.5 text-blue-500 text-xs", title:"windowed to "+winStart+"…"+winEnd}, "◷") : null;
    var titleExtra=windowed ? ("  [windowed "+winStart+"…"+winEnd+"; full-history "+(fmtVal(d[key].value,meta.unit)||"NE")+"]") : (WINDOWED_METRICS[key]?"":"  [full history]");
    if (band==="N/A" || val===null) return h("td",{className:cls+"text-gray-400",key:key,title:meta.label+" — not eligible (insufficient data / field absent)"+titleExtra}, h("span",{className:"italic text-xs"},"NE"), tag);
    return h("td",{className:cls+bandColor(band),key:key,title:meta.label+"  ["+meta.bands+"]  "+meta.desc+titleExtra},
      h("div",{className:"text-sm"}, val, tag),
      sub?h("div",{className:"text-xs text-gray-400 mt-0.5"}, sub):null);
  }

  // ---- Table export (UI-only: reads already-built rows; does NOT touch the compute core) ----
  var EXPORT_METRIC_ORDER = P1_ORDER.concat(P2_ORDER);
  function _exportRows(scope){ return scope==="all" ? masterRows : filtered; }
  function _metricForExport(d, k, scope){
    return (scope!=="all" && winActive && WINDOWED_METRICS[k] && d.win && d.win[k]) ? d.win[k] : d[k];
  }
  function _buildExportMatrix(scope){
    var head=["FLW name","Username","LLO","Country","Versions","Opportunity IDs","Low caseload (<20 cases)","Total cases","Total visits","Red flags","Yellow flags"];
    EXPORT_METRIC_ORDER.forEach(function(k){ var lb=META[k].label; head.push(lb); head.push(lb+" band"); head.push(lb+" n/d"); });
    var mx=[head];
    _exportRows(scope).forEach(function(d){
      var row=[ d.flw_name||d.username||"", d.username||"", d.llo||"", d.country||"", (d.versions||[]).join("/"),
        (d.opportunity_ids||[]).join(" "), d._low_caseload?"yes":"no", d.total_cases, d.total_visits, d.red_count, d.yellow_count ];
      EXPORT_METRIC_ORDER.forEach(function(k){ var m=_metricForExport(d,k,scope)||{}; var v=fmtVal(m.value, META[k].unit);
        row.push(v==null?"NE":v); row.push((m.rag==null||m.rag==="N/A")?"NE":m.rag);
        row.push((m.num!=null&&m.den!=null)?(m.num+"/"+m.den):""); });
      mx.push(row);
    });
    return mx;
  }
  function _c2s(c){ return c==null?"":String(c); }
  function _toCSV(mx){ return mx.map(function(r){ return r.map(function(c){ c=_c2s(c); return /[",\n\r]/.test(c)?('"'+c.replace(/"/g,'""')+'"'):c; }).join(","); }).join("\r\n"); }
  function _toTSV(mx){ return mx.map(function(r){ return r.map(function(c){ return _c2s(c).replace(/[\t\r\n]/g," "); }).join("\t"); }).join("\n"); }
  function _flash(msg){ setCopiedMsg(msg); window.setTimeout(function(){ setCopiedMsg(""); }, 2600); }
  function _stamp(){ var dt=new Date(); function p(x){return (x<10?"0":"")+x;} return dt.getFullYear()+p(dt.getMonth()+1)+p(dt.getDate())+"-"+p(dt.getHours())+p(dt.getMinutes()); }
  function doCopyTable(scope){
    var mx=_buildExportMatrix(scope), tsv=_toTSV(mx), n=mx.length-1, lbl=(scope==="all"?"all FLWs":"current view");
    function ok(){ _flash("Copied "+n+" row"+(n===1?"":"s")+" — "+lbl+" (paste into Sheets/Excel)"); }
    function fb(){ try{ var ta=document.createElement("textarea"); ta.value=tsv; ta.style.position="fixed"; ta.style.top="-9999px"; document.body.appendChild(ta); ta.focus(); ta.select(); var okc=document.execCommand("copy"); document.body.removeChild(ta); okc?ok():_flash("Copy blocked — use Download CSV"); }catch(e){ _flash("Copy blocked — use Download CSV"); } }
    if (navigator.clipboard && navigator.clipboard.writeText){ navigator.clipboard.writeText(tsv).then(ok, fb); } else fb();
  }
  function doDownloadCSV(scope){
    var mx=_buildExportMatrix(scope), csv="﻿"+_toCSV(mx);
    try{ var blob=new Blob([csv],{type:"text/csv;charset=utf-8;"}), url=URL.createObjectURL(blob), a=document.createElement("a");
      a.href=url; a.download="kmc-audit-"+(scope==="all"?"all-flws":"filtered")+"-"+_stamp()+".csv";
      document.body.appendChild(a); a.click(); document.body.removeChild(a); window.setTimeout(function(){ URL.revokeObjectURL(url); }, 1000);
      _flash("Downloaded "+(mx.length-1)+" rows CSV"); }catch(e){ _flash("Download failed"); }
  }

  function bandChip(d, key){
    var m=d[key], meta=META[key]; var band=m.rag; var val=fmtVal(m.value, meta.unit); var sub=fmtSub(m);
    var col=band==="RED"?"bg-red-100 text-red-800 border-red-200":band==="YELLOW"?"bg-amber-100 text-amber-800 border-amber-200":band==="GREEN"?"bg-green-50 text-green-700 border-green-200":"bg-gray-50 text-gray-400 border-gray-200";
    return h("div",{key:key, className:"rounded border px-2 py-1 "+col, title:meta.desc},
      h("div",{className:"text-xs font-medium"}, meta.label),
      h("div",{className:"text-sm"}, val===null?"NE":val),
      h("div",{className:"text-xs opacity-70"}, sub||meta.bands));
  }

  function detailPanel(d){
    var visits=(d._visit_rows||[]).slice().sort(function(a,b){var x=parseDate(rget(a,"visit_date"))||0, y=parseDate(rget(b,"visit_date"))||0; return y-x;}).slice(0,20);
    return h("div",{className:"space-y-4"},
      h("div",null,
        h("div",{className:"text-sm font-semibold text-gray-700 mb-2"}, "Opportunity breakdown"),
        h("div",{className:"text-xs text-gray-500 mb-2"},
          "Visits: "+((d.scheduled_visits||0)+(d.additional_visits||0))+" total — "+(d.scheduled_visits||0)+" scheduled, "
          +(d.additional_visits||0)+" additional"),
        h("div",{className:"flex flex-wrap gap-2"}, d.opportunity_breakdown.map(function(b){ return h("span",{key:b.opportunity_id, className:"text-xs bg-white border border-gray-200 rounded px-2 py-1"}, b.name+" — "+b.total_cases+" cases / "+b.kmc_visit_count+" visits"); }))),
      h("div",null,
        h("div",{className:"text-sm font-semibold text-gray-700 mb-2"}, "All 18 register metrics (value · band · n/d)"),
        h("div",{className:"grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2"}, METRIC_KEYS.map(function(kk){ return bandChip(d, kk); }))),
      h("div",null,
        h("div",{className:"text-sm font-semibold text-gray-700 mb-2"}, "Recent visits ("+(d._visit_rows||[]).length+" total)"),
        h("div",{className:"overflow-x-auto"},
          h("table",{className:"min-w-full text-xs"},
            h("thead",null, h("tr",{className:"text-gray-500"}, ["Date","Case","Visit #","Weight(g)","Danger","Referred","HR","Temp","SpO2","Status"].map(function(hd){return h("th",{key:hd, className:"px-2 py-1 text-left"}, hd);}))),
            h("tbody",null, visits.map(function(v,idx){ return h("tr",{key:idx, className:"border-t border-gray-100"},
              h("td",{className:"px-2 py-1"}, rget(v,"visit_date")||"—"),
              h("td",{className:"px-2 py-1 font-mono"}, String(rget(v,"beneficiary_case_id")||"").slice(0,8)),
              h("td",{className:"px-2 py-1"}, rget(v,"visit_number")==null?"—":rget(v,"visit_number")),
              h("td",{className:"px-2 py-1"}, readWeightG(v)==null?"—":Math.round(readWeightG(v))),
              h("td",{className:"px-2 py-1"}, rget(v,"danger_sign_positive")||"—"),
              h("td",{className:"px-2 py-1"}, rget(v,"child_referred")||"—"),
              h("td",{className:"px-2 py-1"}, rget(v,"heart_rate")==null?"—":rget(v,"heart_rate")),
              h("td",{className:"px-2 py-1"}, rget(v,"temperature")==null?"—":rget(v,"temperature")),
              h("td",{className:"px-2 py-1"}, rget(v,"spo2_level")==null?"—":rget(v,"spo2_level")),
              h("td",{className:"px-2 py-1"}, rget(v,"kmc_status")||"—")); }))))));
  }

  function handleCreateAudits(){
    if (isRunning || selectedCount===0) return;
    setShowModal(false); setIsRunning(true); setProgress({status:"starting", message:"Preparing audits..."});
    var byOpp={}; selectedRows.forEach(function(d){ var op=d.primary_opp; if (!op) return; (byOpp[op]=byOpp[op]||[]).push(d.username); });
    var oppIds=Object.keys(byOpp);
    if (oppIds.length===0){ setIsRunning(false); setProgress({status:"failed", error:"No routable opportunity for selection"}); return; }
    var done=0, failed=0;
    oppIds.forEach(function(op){
      var opNum=parseInt(op,10);
      var aStart=winActive?winStart:startDate, aEnd=winActive?winEnd:endDate;
      var criteria={ audit_type:"date_range", granularity:"per_flw", title:("KMC Flag Audit "+aStart+" to "+aEnd), start_date:aStart, end_date:aEnd, count_per_flw:countPerFlw,
        related_fields:[{imagePath:"anthropometric/upload_weight_image", fieldPath:"child_weight_visit", label:"Weight Reading", filter_by_image:false, filter_by_field:false}],
        selected_flw_user_ids:byOpp[op] };
      actions.createAudit({ opportunities:[{id:opNum, name:(OPP_META[opNum]||{}).name||("Opp "+opNum)}], criteria:criteria, workflow_run_id:instance.id, ai_agent_id: aiAgent==="none"?undefined:aiAgent })
        .then(function(res){ done++; if (!res||!res.success) failed++; if (done===oppIds.length){ setIsRunning(false); setProgress(failed?{status:"failed",error:failed+" group(s) failed"}:{status:"completed",message:"Audits created for "+oppIds.length+" opportunity group(s)"}); if (onUpdateState) onUpdateState({status:"audits_created"}).catch(function(){}); } })
        .catch(function(e){ done++; failed++; if (done===oppIds.length){ setIsRunning(false); setProgress({status:"failed",error:(e&&e.message)||"error"}); } });
    });
  }

  if (flwRows.length===0){
    return h("div",{className:"space-y-6"},
      h("div",{className:"bg-white rounded-lg shadow-sm p-6"}, h("h1",{className:"text-2xl font-bold text-gray-900"}, definition.name), h("p",{className:"text-gray-600 mt-1"}, definition.description)),
      h("div",{className:"bg-gray-50 border border-gray-200 rounded-lg p-8 text-center text-gray-500"}, "No pipeline data yet — run the pipeline to load FLW audit metrics."));
  }

  var headerEl = h("div",{className:"bg-white rounded-lg shadow-sm p-5 flex items-start justify-between gap-4 flex-wrap"},
    h("div",null,
      h("h1",{className:"text-2xl font-bold text-gray-900"}, h("i",{className:"fa-solid fa-flag text-red-500 mr-2"}), definition.name),
      h("p",{className:"text-gray-600 mt-1"}, "18 register FLW-audit metrics across merged V1/V2/V3 opportunities (11 opps · 6 LLOs · 3 countries), banded green / yellow / red. Live data.")),
    h("div",{className:"text-right text-xs text-gray-500 shrink-0", title:"Live data, cached up to ~1 hour. Reload for a refresh, or add ?refresh=1 to the URL to force the very latest."},
      h("div",null, h("i",{className:"fa-regular fa-clock mr-1"}), "Last loaded: ", h("span",{className:"font-semibold text-gray-700"}, freshness.loaded)),
      freshness.latestVisit ? h("div",{className:"mt-0.5"}, "Latest visit in data: ", h("span",{className:"font-semibold text-gray-700"}, freshness.latestVisit)) : null));

  var kpiDefs=[["FLWs Loaded", kpi.loaded, "blue"],["≥1 Red", kpi.anyRed, "red"],["≥1 Yellow", kpi.anyYellow, "amber"],["Low caseload (<20)", kpi.excluded, "gray"],["KMC Visits", kpi.totalVisits.toLocaleString(), "green", (kpi.totalVisits-kpi.addVisits).toLocaleString()+" scheduled · "+kpi.addVisits.toLocaleString()+" additional"],["Total Cases", kpi.totalCases.toLocaleString(), "teal"]];
  var kpiEl = h("div",{className:"grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3"}, kpiDefs.map(function(c){
    return h("div",{key:c[0], className:"bg-white rounded-lg shadow-sm p-4 border-l-4 border-"+c[2]+"-500"}, h("div",{className:"text-2xl font-bold text-gray-900"}, c[1]), h("div",{className:"text-xs text-gray-600 mt-1"}, c[0]),
      c[3] ? h("div",{className:"text-[11px] text-gray-400 mt-0.5"}, c[3]) : null);
  }));

  var filterEl = h("div",{className:"bg-white rounded-lg shadow-sm p-3 flex flex-wrap items-center gap-3"},
    h("div",{className:"flex gap-2"}, [["all","All"],["any_red","Any Red"],["two_red","2+ Red"],["any_yellow","Any Yellow"]].map(function(f){
      return h("button",{key:f[0], onClick:function(){setFilter(f[0]);}, className:"px-3 py-1.5 text-sm rounded-full border "+(filter===f[0]?"bg-blue-600 text-white border-blue-600":"bg-white text-gray-700 border-gray-300 hover:border-blue-400")}, f[1]);
    })),
    h("select",{value:lloFilter, onChange:function(e){setLloFilter(e.target.value);}, className:"border border-gray-300 rounded-lg px-2 py-1.5 text-sm"},
      h("option",{value:"all"},"All LLOs"), h("option",{value:"PIPN"},"PIPN"), h("option",{value:"NAMA"},"NAMA"), h("option",{value:"GHI"},"GHI"), h("option",{value:"Kikapu"},"Kikapu"), h("option",{value:"EHA"},"EHA"), h("option",{value:"BERI"},"BERI")),
    h("select",{value:verFilter, onChange:function(e){setVerFilter(e.target.value);}, className:"border border-gray-300 rounded-lg px-2 py-1.5 text-sm", title:"Filter by app version"},
      h("option",{value:"all"},"All versions"), h("option",{value:"V1"},"V1 (V0/V1)"), h("option",{value:"V2"},"V2"), h("option",{value:"V3"},"V3")),
    h("select",{value:winPreset, onChange:function(e){applyPreset(e.target.value);}, className:"border border-gray-300 rounded-lg px-2 py-1.5 text-sm"+(winActive?" border-blue-400 text-blue-700":""), title:"Date window — scopes the 6 ◷ reading-quality flags + the audit + the FLW list. Cohort flags stay full history."},
      h("option",{value:"all"},"◷ All time"), h("option",{value:"last_week"},"◷ Last 7 days"), h("option",{value:"last_2_weeks"},"◷ Last 14 days"), h("option",{value:"last_month"},"◷ Last 30 days"), h("option",{value:"custom"},"◷ Custom…")),
    winPreset==="custom" ? h("input",{type:"date", value:winStart, max:winEnd||undefined, onChange:function(e){setWinStart(e.target.value);}, className:"border border-gray-300 rounded-lg px-2 py-1.5 text-sm", title:"Window start"}) : null,
    winPreset==="custom" ? h("input",{type:"date", value:winEnd, min:winStart||undefined, onChange:function(e){setWinEnd(e.target.value);}, className:"border border-gray-300 rounded-lg px-2 py-1.5 text-sm", title:"Window end"}) : null,
    h("input",{type:"text", placeholder:"Search FLW...", value:search, onChange:function(e){setSearch(e.target.value);}, className:"flex-1 min-w-40 border border-gray-300 rounded-lg px-3 py-1.5 text-sm"}),
    h("label",{className:"flex items-center gap-2 text-sm text-gray-700"}, h("input",{type:"checkbox", checked:showP2, onChange:function(e){setShowP2(e.target.checked);}}), "Show Priority-2 metrics"));

  // ---- Per-indicator slice. Stack as many of the 18 metrics as you like, each with its own band;
  // the table, the footer count and the CSV export all narrow to the result. The chips beside each
  // condition are the four band counts you would get by clicking them — they are computed off the
  // same base as the table, so chip and row count never disagree.
  var _bandChipCls={GREEN:"bg-green-100 text-green-800",YELLOW:"bg-amber-100 text-amber-800",
    RED:"bg-red-100 text-red-800","N/A":"bg-gray-100 text-gray-600"};
  var _modeBtn=function(on){ return "px-2 py-0.5 rounded font-semibold border "+(on?"bg-blue-600 text-white border-blue-600":"bg-white text-gray-600 border-gray-300 hover:border-blue-400"); };
  var _unused=[]; for (var _ui=0;_ui<METRIC_KEYS.length;_ui++){ var _uk=METRIC_KEYS[_ui], _seen=false;
    for (var _uj=0;_uj<metricConds.length;_uj++){ if (metricConds[_uj].k===_uk) _seen=true; }
    if (!_seen) _unused.push(_uk); }
  var bandOptions=[h("option",{key:"RED",value:"RED"},"Red only"), h("option",{key:"YELLOW",value:"YELLOW"},"Yellow only"),
    h("option",{key:"GREEN",value:"GREEN"},"Green only"), h("option",{key:"NA",value:"N/A"},"Not eligible"),
    h("option",{key:"flag",value:"flag"},"Red or Yellow"), h("option",{key:"any",value:"any"},"Any band")];
  var indicatorEl = h("div",{className:"bg-white rounded-lg shadow-sm p-3 space-y-2"},
    h("div",{className:"flex flex-wrap items-center gap-3"},
      h("span",{className:"text-xs font-semibold uppercase tracking-wide text-gray-400"}, "Indicators"),
      h("select",{value:"", onChange:function(e){ if(e.target.value) addCond(e.target.value); },
        className:"border border-gray-300 rounded-lg px-2 py-1.5 text-sm"+(metricConds.length?" border-blue-400 text-blue-700":""),
        title:"Narrow the table to FLWs sitting in a given band on this indicator"},
        [h("option",{key:"_",value:""}, metricConds.length ? "+ add another indicator…" : "+ filter by an indicator…")]
          .concat(_unused.map(function(k){ return h("option",{key:k,value:k}, META[k].label+(PRIORITY[k]===1?"":" (P2)")); }))),
      metricConds.length>1 ? h("div",{className:"flex items-center gap-1 text-xs"},
        h("span",{className:"text-gray-500"}, "FLW must match"),
        h("button",{onClick:function(){setCondMode("all");}, className:_modeBtn(condMode==="all"), title:"Only FLWs meeting every condition"}, "ALL"),
        h("button",{onClick:function(){setCondMode("any");}, className:_modeBtn(condMode==="any"), title:"FLWs meeting at least one condition"}, "ANY")) : null,
      metricConds.length
        ? h("button",{onClick:function(){setMetricConds([]);}, className:"text-xs underline text-gray-500 hover:text-gray-800 ml-auto"}, "clear indicators")
        : h("span",{className:"text-xs text-gray-400 ml-auto"},
            "pick one or more indicators to count, list and export FLWs by band · adding one sorts the table by it · any column header sorts")),
    metricConds.length ? h("div",{className:"space-y-1.5 pt-1 border-t border-gray-100"},
      metricConds.map(function(c, ci){
        var t=metricTallyView[c.k]||{};
        return h("div",{key:c.k, className:"flex flex-wrap items-center gap-2 pl-2 border-l-4 border-blue-300"},
          h("span",{className:"text-sm font-semibold text-gray-800"}, META[c.k].label),
          h("select",{value:c.b, onChange:function(e){ setCondBand(ci, e.target.value); },
            className:"border border-gray-300 rounded-lg px-2 py-1 text-sm"}, bandOptions),
          h("div",{className:"flex flex-wrap items-center gap-1.5"},
            ["GREEN","YELLOW","RED","N/A"].map(function(b){
              var n=t[b]||0;
              return h("button",{key:b, onClick:function(){setCondBand(ci,b);},
                className:"px-2 py-0.5 rounded text-xs font-semibold "+_bandChipCls[b]+(c.b===b?" ring-2 ring-blue-400":""),
                title:"Show the "+n+" FLW"+(n===1?"":"s")+" whose "+META[c.k].label+" is "+bandWord(b)+" (within the filters already applied)"},
                n+" "+(b==="N/A"?"NE":b.charAt(0)+b.slice(1).toLowerCase()));
            })),
          h("span",{className:"text-xs text-gray-500"}, META[c.k].bands),
          h("button",{onClick:function(){ setSortKey(c.k); setSortAsc(false); },
            className:"text-xs underline text-gray-400 hover:text-blue-700", title:"Sort the table by this indicator, worst first"}, "sort by this"),
          h("button",{onClick:function(){ removeCond(ci); }, className:"ml-auto text-gray-400 hover:text-red-600 px-1",
            title:"Remove this condition"}, "✕"));
      })) : null);

  var exportBarEl = h("div",{className:"bg-white rounded-lg shadow-sm px-3 py-2 flex flex-wrap items-center gap-2"},
    h("span",{className:"text-xs font-semibold text-gray-500 uppercase tracking-wide mr-1"}, h("i",{className:"fa-solid fa-file-export mr-1"}), "Export"),
    h("select",{value:exportScope, onChange:function(e){setExportScope(e.target.value);}, className:"border border-gray-300 rounded-lg px-2 py-1.5 text-sm", title:"Choose what to export"},
      h("option",{value:"view"},"Current view — "+filtered.length+" FLW"+(filtered.length===1?"":"s")+" (filters applied)"),
      h("option",{value:"all"},"All FLWs — "+masterRows.length+" (no filters)")),
    h("button",{onClick:function(){doCopyTable(exportScope);}, className:"px-3 py-1.5 text-sm rounded-lg border border-gray-300 bg-white text-gray-700 hover:border-blue-400 hover:text-blue-700"}, h("i",{className:"fa-regular fa-clipboard mr-1.5"}), "Copy table"),
    h("button",{onClick:function(){doDownloadCSV(exportScope);}, className:"px-3 py-1.5 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700"}, h("i",{className:"fa-solid fa-download mr-1.5"}), "Download CSV"),
    copiedMsg ? h("span",{className:"text-sm text-green-600 ml-1"}, h("i",{className:"fa-solid fa-check mr-1"}), copiedMsg) : null,
    h("span",{className:"text-xs text-gray-400 ml-auto"}, "all 18 metrics · value · band · n/d"+(winActive?" · current-view honors the ◷ window; all-FLWs is full history":"")));

  var cols = P1_ORDER.concat(showP2?P2_ORDER:[]);
  // Tint the header of any column being filtered on — 18 columns is too many to find by eye.
  var condKeys={}; for (var _ck=0;_ck<metricConds.length;_ck++){ condKeys[metricConds[_ck].k]=true; }
  var headerCells=[ h("th",{key:"_chk", className:"px-2 py-3 w-8"}),
    h("th",{key:"_name", className:thBase+" text-left", onClick:function(){toggleSort("name");}}, "FLW", SortArrow("name")),
    h("th",{key:"_llo", className:thBase+" text-left"}, "LLO · Ver"),
    h("th",{key:"_cases", className:thBase+" text-center", onClick:function(){toggleSort("cases");}}, "Cases", SortArrow("cases")) ];
  cols.forEach(function(f){ var wm=WINDOWED_METRICS[f]; headerCells.push(h("th",{key:f, className:thBase+" text-center"+(condKeys[f]?" bg-blue-100 text-blue-800":PRIORITY[f]===2?" bg-gray-100":""), onClick:function(){toggleSort(f);}, title:META[f].label+"  ["+META[f].bands+"]\n"+META[f].desc+(wm?"\n(◷ windowed when a date range is set)":"\n(full history — not affected by the date range)")}, META[f].label, h("span",{className:"ml-1 "+(wm?"text-blue-400":"text-gray-300")}, wm?"◷":"ⓘ"), SortArrow(f))); });
  headerCells.push(h("th",{key:"_red", className:thBase+" text-center", onClick:function(){toggleSort("red");}}, "R/Y", SortArrow("red")));

  var bodyRows=[];
  filtered.forEach(function(d){
    var kk=rowKey(d);
    var border=d.red_count>=2?"border-l-4 border-red-500":d.red_count===1?"border-l-4 border-orange-400":d.yellow_count>=1?"border-l-4 border-amber-300":"";
    var cells=[ h("td",{key:"_chk", className:"px-2 py-2 text-center"}, h("input",{type:"checkbox", checked:!!selected[kk], onChange:function(){toggleSelect(d);}, disabled:isRunning})),
      h("td",{key:"_name", className:"px-2 py-2 text-sm cursor-pointer", onClick:function(){setExpanded(expanded===kk?null:kk);}},
        h("div",{className:"font-medium text-gray-900 flex items-center gap-1"}, h("i",{className:"fa-solid "+(expanded===kk?"fa-caret-down":"fa-caret-right")+" text-gray-400"}), d.flw_name),
        (d.flw_name!==d.username)?h("div",{className:"text-xs text-gray-400 font-mono"}, d.username):null),
      h("td",{key:"_llo", className:"px-2 py-2 text-sm whitespace-nowrap"}, h("span",{className:"px-2 py-0.5 rounded text-xs bg-indigo-50 text-indigo-700"}, d.llo), h("span",{className:"ml-1 text-xs text-gray-400", title:"App versions this FLW spans"}, (d.versions||[]).join("/"))),
      h("td",{key:"_cases", className:"px-2 py-2 text-sm text-center", title:d.opportunity_breakdown.map(function(b){return b.name+": "+b.total_cases+" cases";}).join(" | ")}, d.total_cases) ];
    cols.forEach(function(f){ cells.push(metricCell(d,f)); });
    cells.push(h("td",{key:"_red", className:"px-2 py-2 text-center"},
      h("span",{className:"inline-flex items-center gap-1 justify-center"},
        h("span",{className:"inline-flex items-center justify-center w-6 h-6 rounded-full text-white text-xs font-bold "+(d.red_count>=2?"bg-red-500":d.red_count===1?"bg-orange-400":"bg-gray-300"), title:d.red_count+" red"}, d.red_count),
        d.yellow_count>0?h("span",{className:"inline-flex items-center justify-center w-6 h-6 rounded-full bg-amber-100 text-amber-700 text-xs font-semibold", title:d.yellow_count+" yellow"}, d.yellow_count):null)));
    bodyRows.push(h("tr",{key:kk, className:(selected[kk]?"bg-blue-50 ":"hover:bg-gray-50 ")+border}, cells));
    if (expanded===kk){
      var colSpan=4+cols.length+1;
      bodyRows.push(h("tr",{key:kk+"_d", className:"bg-gray-50"}, h("td",{colSpan:colSpan, className:"px-6 py-4"}, detailPanel(d))));
    }
  });

  var tableEl = h("div",{className:"bg-white rounded-lg shadow-sm overflow-x-auto"},
    h("table",{className:"min-w-full divide-y divide-gray-200"},
      h("thead",{className:"bg-gray-50"}, h("tr",null, headerCells)),
      h("tbody",{className:"bg-white divide-y divide-gray-200"}, bodyRows)),
    h("div",{className:"px-4 py-2 text-xs text-gray-500"}, filtered.length+" FLW"+(filtered.length!==1?"s":"")+" shown"
      +(metricConds.length ? " · "+metricConds.map(function(c){ return META[c.k].label+" = "+bandWord(c.b); }).join(condMode==="any"?" OR ":" AND ") : "")
      +" · click any column header to sort · bands per KMC Audit & Metrics Flag Register · NE = not eligible (below the register's minimum data for that metric, or the field is not captured by that opp's app)"));

  var progressEl = progress ? h("span",{className:"text-sm "+(progress.status==="failed"?"text-red-600":progress.status==="completed"?"text-green-600":"text-blue-600")},
    progress.status==="completed"?("✓ "+progress.message):progress.status==="failed"?("⚠ "+(progress.error||"Failed")):h("span",null, h("i",{className:"fa-solid fa-spinner fa-spin mr-1"}), progress.message)) : null;
  var actionBar = h("div",{className:"sticky bottom-0 bg-white border-t border-gray-200 shadow-lg p-3 -mx-4 sm:-mx-6 lg:-mx-8"},
    h("div",{className:"max-w-7xl mx-auto flex items-center justify-between gap-4"},
      h("div",{className:"flex items-center gap-4"}, h("span",{className:"text-sm text-gray-600"}, selectedCount+" FLW"+(selectedCount!==1?"s":"")+" selected"), progressEl),
      h("button",{onClick:function(){setShowModal(true);}, disabled:selectedCount===0||isRunning, className:"px-5 py-2.5 rounded-lg text-sm font-medium "+((selectedCount===0||isRunning)?"bg-gray-300 text-gray-500 cursor-not-allowed":"bg-red-600 text-white hover:bg-red-700")},
        isRunning?h("span",null,h("i",{className:"fa-solid fa-spinner fa-spin mr-2"}),"Creating..."):h("span",null,h("i",{className:"fa-solid fa-plus mr-2"}),"Create Audits ("+selectedCount+")"))));

  var modal = showModal ? h("div",{className:"fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50", onClick:function(e){ if (e.target===e.currentTarget) setShowModal(false); }},
    h("div",{className:"bg-white rounded-xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden"},
      h("div",{className:"px-6 py-4 bg-gray-50 border-b border-gray-200"}, h("h3",{className:"text-lg font-semibold text-gray-900"}, "Configure Audit"), h("p",{className:"text-sm text-gray-500 mt-1"}, "Creating audits for "+selectedCount+" selected FLW"+(selectedCount!==1?"s":"")+" (routed per opportunity)")),
      h("div",{className:"px-6 py-5 space-y-4"},
        h("div",{className:"flex gap-3"},
          h("div",{className:"flex-1"}, h("label",{className:"block text-xs text-gray-500 mb-1"},"Start"), h("input",{type:"date", value:startDate, onChange:function(e){setStartDate(e.target.value);}, className:"w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"})),
          h("div",{className:"flex-1"}, h("label",{className:"block text-xs text-gray-500 mb-1"},"End"), h("input",{type:"date", value:endDate, onChange:function(e){setEndDate(e.target.value);}, className:"w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"}))),
        h("div",null, h("label",{className:"block text-sm font-medium text-gray-700 mb-1"},"Visits to review per FLW"), h("input",{type:"number", min:"1", max:"50", value:countPerFlw, onChange:function(e){setCountPerFlw(parseInt(e.target.value)||10);}, className:"w-24 border border-gray-300 rounded-lg px-3 py-2 text-sm"})),
        h("div",null, h("label",{className:"block text-sm font-medium text-gray-700 mb-1"},"AI Review Agent"), h("select",{value:aiAgent, onChange:function(e){setAiAgent(e.target.value);}, className:"w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"}, h("option",{value:"scale_validation"},"Scale Validation (weight image review)"), h("option",{value:"none"},"No AI Review")))),
      h("div",{className:"px-6 py-4 bg-gray-50 border-t border-gray-200 flex justify-end gap-3"},
        h("button",{onClick:function(){setShowModal(false);}, className:"px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"},"Cancel"),
        h("button",{onClick:handleCreateAudits, disabled:!startDate||!endDate, className:"px-5 py-2 text-sm font-medium rounded-lg "+((!startDate||!endDate)?"bg-gray-300 text-gray-500 cursor-not-allowed":"bg-red-600 text-white hover:bg-red-700")}, "Create Audits ("+selectedCount+")")))) : null;

  var tabBar = h("div",{className:"flex gap-1 bg-gray-100 p-1 rounded-lg"}, [["overview","Overview"],["detail","FLW Detail"]].map(function(t){
    var active=activeTab===t[0];
    return h("button",{key:t[0], onClick:function(){setActiveTab(t[0]);}, className:"flex-1 py-2 px-3 rounded-md text-sm font-medium transition-colors "+(active?"bg-white text-gray-900 shadow-sm":"text-gray-600 hover:text-gray-800")}, t[1]);
  }));

  var COUNTRY_ORDER=["Uganda","Kenya","Nigeria","Other"];
  var pctRed = overview.analyzedN>0 ? Math.round(100*overview.flaggedRedN/overview.analyzedN) : 0;

  // ---- Indicator scoreboard: all 18 indicators x Green/Yellow/Red/Not-eligible in one grid.
  // Every number is a button that opens the FLW Detail tab already filtered to that indicator and
  // band, so "22 FLWs are RED on early discharge" is one click away from the list of who they are.
  var scoreCell = function(k, band, n){
    var cls = band==="RED" ? "text-red-700 hover:bg-red-50" : band==="YELLOW" ? "text-amber-700 hover:bg-amber-50"
      : band==="GREEN" ? "text-green-700 hover:bg-green-50" : "text-gray-400 hover:bg-gray-50";
    return h("td",{key:band, className:"px-2 py-1 text-center"},
      n>0 ? h("button",{onClick:function(){focusMetric(k,band);}, className:"w-full rounded px-2 py-0.5 font-semibold "+cls,
        title:"List the "+n+" FLW"+(n===1?"":"s")+" whose "+META[k].label+" is "+(band==="N/A"?"not eligible":band.toLowerCase())}, n)
        : h("span",{className:"text-gray-300"},"–"));
  };
  var scoreboardEl = h("div",{className:"bg-white rounded-lg shadow-sm overflow-hidden"},
    h("div",{className:"px-4 py-3 border-b border-gray-100 flex items-center justify-between flex-wrap gap-2"},
      h("span",{className:"text-sm font-semibold text-gray-800"}, "Indicator scoreboard — how many FLWs sit in each band"),
      h("span",{className:"text-xs text-gray-400"}, "click any number to list those FLWs")),
    h("div",{className:"overflow-x-auto"},
      h("table",{className:"min-w-full text-sm"},
        h("thead",{className:"bg-gray-50 text-xs text-gray-500 uppercase"},
          h("tr",null, ["Indicator","Green","Yellow","Red","Not eligible","Bands"].map(function(hd,hi){
            return h("th",{key:hd, className:"px-2 py-2 font-medium whitespace-nowrap "+(hi===0||hi===5?"text-left":"text-center")}, hd); }))),
        h("tbody",null, METRIC_KEYS.filter(function(k){ return showP2 || PRIORITY[k]===1; }).map(function(k){
          var t=metricTally[k]||{GREEN:0,YELLOW:0,RED:0,"N/A":0};
          return h("tr",{key:k, className:"border-t border-gray-100 hover:bg-gray-50"},
            h("td",{className:"px-2 py-1 whitespace-nowrap"},
              h("span",{className:"font-medium text-gray-900"}, META[k].label),
              h("span",{className:"text-xs text-gray-400 ml-1.5"}, PRIORITY[k]===1?"P1":"P2")),
            scoreCell(k,"GREEN",t.GREEN), scoreCell(k,"YELLOW",t.YELLOW), scoreCell(k,"RED",t.RED), scoreCell(k,"N/A",t["N/A"]),
            h("td",{className:"px-2 py-1 text-xs text-gray-500 whitespace-nowrap"}, META[k].bands));
        })))),
    h("div",{className:"px-4 py-2 text-xs text-gray-500"},
      "Counts follow the LLO, version and date-window filters. Tick \"Show Priority-2 metrics\" in FLW Detail to include the P2 rows here too."));

  // 1. Program-at-a-glance banner
  var glanceEl = h("div",{className:"bg-white rounded-lg shadow-sm p-5 border-l-4 border-slate-700"},
    h("div",{className:"text-xs uppercase tracking-wide text-gray-400 mb-1"}, "Program at a glance"),
    h("div",{className:"text-lg md:text-xl font-bold text-gray-900"}, kpi.loaded+" FLWs · "+kpi.totalCases.toLocaleString()+" SVN cases · "+kpi.totalVisits.toLocaleString()+" KMC visits"),
    h("div",{className:"text-sm text-gray-500 mt-0.5"}, "11 opportunities · 6 LLO partners · 3 countries (Uganda, Kenya, Nigeria) · app versions V0–V3"),
    h("div",{className:"text-sm text-gray-700 mt-3 flex flex-wrap gap-x-2 gap-y-1 items-center"},
      h("span",{className:"font-bold text-red-600"}, overview.flaggedRedN),
      h("span",null, "of "+overview.analyzedN+" analyzed FLWs ("+pctRed+"%) carry ≥1 red flag"),
      h("span",{className:"text-gray-300"}, "•"),
      h("span",{className:"font-bold text-green-700"}, overview.cleanN), h("span",null,"clean (no red/yellow)"),
      h("span",{className:"text-gray-300"}, "•"),
      h("span",{className:"font-bold text-gray-500"}, kpi.excluded), h("span",null,"with a low caseload (<20 cases) — still scored on whatever clears each metric's minimum")));

  // 2. Concern-category cards — what KIND of problem
  var catColors={"Fraud / data integrity":"border-red-400","Clinical quality & skill":"border-amber-400","Model adherence":"border-blue-400"};
  var catCardsEl = h("div",{className:"grid grid-cols-1 md:grid-cols-3 gap-3"},
    CAT_ORDER.map(function(cat){
      return h("div",{key:cat, className:"bg-white rounded-lg shadow-sm p-4 border-t-4 "+(catColors[cat]||"border-gray-300")},
        h("div",{className:"flex items-baseline gap-2"},
          h("span",{className:"text-3xl font-bold text-gray-900"}, overview.catRed[cat]||0),
          h("span",{className:"text-xs text-gray-400"}, "FLWs ≥1 red")),
        h("div",{className:"text-sm font-semibold text-gray-800 mt-1"}, cat),
        h("div",{className:"text-xs text-gray-500 mt-1 leading-snug"}, CAT_DESC[cat]));
    }));

  // 3. Charts
  var chartsEl = h("div",{className:"grid grid-cols-1 lg:grid-cols-2 gap-4"},
    h("div",{className:"bg-white rounded-lg shadow-sm p-4"}, h("div",{className:"text-sm font-semibold text-gray-700 mb-2"}, "FLW status by LLO"), h("div",{style:{height:"260px"}}, h("canvas",{ref:byLloRef}))),
    h("div",{className:"bg-white rounded-lg shadow-sm p-4"}, h("div",{className:"text-sm font-semibold text-gray-700 mb-2"}, "Top red-firing flags (across analyzed FLWs)"), h("div",{style:{height:"260px"}}, h("canvas",{ref:topFlagRef}))));

  // 4. Highest-risk FLWs — audit-first worklist
  var riskRows = overview.risk.slice(0,12);
  var riskEl = h("div",{className:"bg-white rounded-lg shadow-sm overflow-hidden"},
    h("div",{className:"px-4 py-3 border-b border-gray-100 flex items-center justify-between"},
      h("span",{className:"text-sm font-semibold text-gray-800"}, "Highest-risk FLWs — audit these first"),
      h("span",{className:"text-xs text-gray-400"}, overview.flaggedRedN+" red-flagged in current filter")),
    h("div",{className:"overflow-x-auto"},
      h("table",{className:"min-w-full text-sm"},
        h("thead",{className:"bg-gray-50 text-xs text-gray-500 uppercase"},
          h("tr",null, ["FLW","LLO · Country","Cases","Red","Yellow","Top red flags"].map(function(hd){ return h("th",{key:hd, className:"px-3 py-2 text-left font-medium whitespace-nowrap"}, hd); }))),
        h("tbody",null,
          riskRows.length ? riskRows.map(function(x,i){
            return h("tr",{key:i, className:"border-t border-gray-100 hover:bg-gray-50"},
              h("td",{className:"px-3 py-2 font-medium text-gray-900 whitespace-nowrap"}, x.name),
              h("td",{className:"px-3 py-2 text-gray-600 whitespace-nowrap"}, x.llo+" · "+x.country),
              h("td",{className:"px-3 py-2 text-gray-700"}, x.cases),
              h("td",{className:"px-3 py-2"}, h("span",{className:"inline-flex items-center justify-center h-6 px-2 rounded-full bg-red-500 text-white text-xs font-bold"}, x.red)),
              h("td",{className:"px-3 py-2"}, x.yellow>0 ? h("span",{className:"inline-flex items-center justify-center h-6 px-2 rounded-full bg-amber-400 text-white text-xs font-bold"}, x.yellow) : h("span",{className:"text-gray-300"},"–")),
              h("td",{className:"px-3 py-2 text-xs text-gray-600"}, x.flags.slice(0,6).join(", ")+(x.flags.length>6?"  +"+(x.flags.length-6)+" more":"")));
          }) : h("tr",null, h("td",{colSpan:6, className:"px-3 py-6 text-center text-gray-400"}, "No red-flagged FLWs in the current filter"))))));

  // 5. Country -> LLO rollup
  var rollupEl = COUNTRY_ORDER.filter(function(c){ return overview.byC[c]; }).map(function(c){
      var llos=overview.byC[c];
      return h("div",{key:c, className:"bg-white rounded-lg shadow-sm p-4"},
        h("div",{className:"text-sm font-bold text-gray-800 mb-3"}, c),
        h("div",{className:"grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3"},
          Object.keys(llos).map(function(l){ var s=llos[l];
            return h("div",{key:l, className:"border border-gray-200 rounded-lg p-3"},
              h("div",{className:"flex items-center justify-between mb-2"}, h("span",{className:"font-semibold text-gray-800"}, l), h("span",{className:"text-xs text-gray-400"}, s.flws+" FLWs")),
              h("div",{className:"flex flex-wrap gap-1"},
                h("span",{className:"px-2 py-0.5 rounded text-xs bg-red-100 text-red-700"}, s.red+" red"),
                h("span",{className:"px-2 py-0.5 rounded text-xs bg-amber-100 text-amber-700"}, s.yellow+" yellow"),
                h("span",{className:"px-2 py-0.5 rounded text-xs bg-green-100 text-green-700"}, s.clean+" clean"),
                h("span",{className:"px-2 py-0.5 rounded text-xs bg-gray-100 text-gray-500"}, s.excluded+" low")));
          })));
    });

  var overviewEl = h("div",{className:"space-y-5"}, glanceEl, catCardsEl, chartsEl, scoreboardEl, riskEl,
    h("div",{className:"space-y-4"}, h("div",{className:"text-sm font-bold text-gray-700"}, "Coverage by country → LLO"), rollupEl));

  var winBannerEl = winActive ? h("div",{className:"bg-blue-50 border border-blue-200 rounded-lg px-3 py-2 text-sm text-blue-800 flex items-center flex-wrap gap-x-2 gap-y-1"},
    h("span",{className:"font-semibold"}, "◷ Window: "+winStart+" → "+winEnd),
    h("span",{className:"text-blue-600"}, "· "+scoped.length+" FLW"+(scoped.length===1?"":"s")+" active · the 6 ◷ flags are windowed to this range; all other flags stay full-history · a created audit uses this window"),
    h("button",{onClick:function(){applyPreset("all");}, className:"ml-auto text-xs underline hover:text-blue-900"}, "clear window")) : null;

  return h("div",{className:"space-y-5 pb-28"}, headerEl, kpiEl, tabBar, winBannerEl,
    (activeTab==="overview") ? overviewEl : h("div",{className:"space-y-5"}, filterEl, indicatorEl, exportBarEl, tableEl),
    (activeTab==="detail") ? actionBar : null, modal);
}
"""


TEMPLATE = {
    "key": "kmc_audit_dashboard",
    "name": "KMC Audit Dashboard",
    "description": (
        "18-metric register-faithful KMC FLW audit across merged V1/V2/V3 opportunities. "
        "3-tier RAG bands, drilldown, one-click audit creation."
    ),
    "icon": "fa-flag",
    "color": "red",
    "multi_opp": True,
    "definition": DEFINITION,
    "render_code": RENDER_CODE,
    "pipeline_schemas": PIPELINE_SCHEMAS,
}
