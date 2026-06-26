"""
KMC Audit Dashboard workflow template (multi-opportunity, action-shaped).

Ports the local ``custom_analysis/kmc_audit`` dashboard to a live Labs workflow
template. Computes the full 16-flag-per-FLW audit over MERGED V1+V2 opportunity
data (multi-opp: rows are tagged with opportunity_id and concatenated by the
engine; the render merges them per (LLO, username)).

Two pipelines (connect_csv):
- ``flw_flags``     AGGREGATED — per-FLW case/visit/danger counts.
- ``weight_series`` VISIT_LEVEL — per-visit rows for weight pairs, mortality,
  enrollment, vitals, GPS, referral.

The render code's compute core (deriveFlags + buildMasterRows) is a byte-exact
JS port of ``flag_logic.py`` / ``data_access.py``, validated against a golden
reference (see .kmc_validation/: 612 flag + 792 metric assertions, PASS).

Field paths verified live against PIPN V1 (524) + V2 (874): all resolve,
weight is grams (JS auto-detects kg<50 vs grams), kmc_status closure code is
"discharged", mortality via child_alive="no".
"""

PIPELINE_SCHEMAS = [
    {
        "alias": "flw_flags",
        "name": "KMC Audit \u2014 FLW Aggregated",
        "description": "Per-FLW aggregated counts: distinct cases, KMC visits, danger-sign visits/positives",
        "schema": {
            "data_source": {"type": "connect_csv"},
            "grouping_key": "username",
            "terminal_stage": "aggregated",
            "linking_field": "beneficiary_case_id",
            "fields": [
                {
                    "name": "total_cases",
                    "paths": ["form.kmc_beneficiary_case_id", "form.case.@case_id"],
                    "aggregation": "count_distinct",
                    "description": "Distinct beneficiary case IDs",
                },
                {
                    "name": "kmc_visit_count",
                    "path": "form.grp_kmc_visit.visit_number",
                    "aggregation": "count",
                    "description": "KMC visits where visit_number is populated",
                },
                {
                    "name": "danger_visit_count",
                    "paths": [
                        "form.danger_signs_checklist.danger_sign_positive",
                        "form.child_details.Danger_Signs_Checklist.danger_sign_positive",
                    ],
                    "aggregation": "count",
                    "description": "Visits where danger-sign checklist filled",
                },
                {
                    "name": "danger_positive_count",
                    "paths": [
                        "form.danger_signs_checklist.danger_sign_positive",
                        "form.child_details.Danger_Signs_Checklist.danger_sign_positive",
                    ],
                    "aggregation": "count",
                    "filter_path": "form.danger_signs_checklist.danger_sign_positive",
                    "filter_value": "yes",
                    "description": "Visits where any danger sign positive",
                },
            ],
            "histograms": [],
            "filters": {},
        },
    },
    {
        "alias": "weight_series",
        "name": "KMC Audit \u2014 Visit Level",
        "description": "Per-visit rows for weight pairs, mortality, enrollment, danger/referral, vitals, GPS",
        "schema": {
            "data_source": {"type": "connect_csv"},
            "grouping_key": "username",
            "terminal_stage": "visit_level",
            "linking_field": "beneficiary_case_id",
            "fields": [
                {
                    "name": "beneficiary_case_id",
                    "paths": ["form.kmc_beneficiary_case_id", "form.case.@case_id"],
                    "aggregation": "first",
                },
                {
                    "name": "visit_date",
                    "path": "form.grp_kmc_visit.visit_date",
                    "aggregation": "first",
                    "transform": "date",
                },
                {
                    "name": "weight",
                    "paths": [
                        "form.anthropometric.child_weight_visit",
                        "form.child_details.birth_weight_reg.child_weight_reg",
                    ],
                    "aggregation": "first",
                    "transform": "float",
                },
                {
                    "name": "visit_number",
                    "path": "form.grp_kmc_visit.visit_number",
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
                    "paths": ["form.grp_kmc_beneficiary.kmc_status", "form.kmc_status"],
                    "aggregation": "first",
                },
                {
                    "name": "danger_sign_positive",
                    "paths": [
                        "form.danger_signs_checklist.danger_sign_positive",
                        "form.child_details.Danger_Signs_Checklist.danger_sign_positive",
                    ],
                    "aggregation": "first",
                },
                {"name": "child_alive", "path": "form.child_alive", "aggregation": "first"},
                {"name": "child_referred", "path": "form.case.update.child_referred", "aggregation": "first"},
                {
                    "name": "temperature",
                    "path": "form.danger_signs_checklist.svn_temperature",
                    "aggregation": "first",
                    "transform": "float",
                },
                {
                    "name": "gps",
                    "paths": ["form.visit_gps_manual", "form.reg_gps", "metadata.location"],
                    "aggregation": "first",
                },
                {
                    "name": "heart_rate",
                    "paths": [
                        "form.danger_signs_checklist.child_heart_rate",
                        "form.child_details.Danger_Signs_Checklist.child_heart_rate",
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
            ],
            "histograms": [],
            "filters": {},
        },
    },
]

DEFINITION = {
    "name": "KMC Audit Dashboard",
    "description": (
        "16-flag KMC FLW audit across merged V1+V2 opportunities (live). "
        "Priority + secondary flag tiers, per-FLW drilldown, one-click audit creation."
    ),
    "version": 1,
    "templateType": "kmc_audit_dashboard",
    "statuses": [
        {"id": "pending", "label": "Pending Review", "color": "gray"},
        {"id": "audits_created", "label": "Audits Created", "color": "green"},
    ],
    "config": {"multi_opp": True, "showSummaryCards": False, "showFilters": False},
    "pipeline_sources": [],
}

RENDER_CODE = r"""/* KMC Audit Dashboard — workflow RENDER_CODE (multi-opp, action-shaped, live).
 * Compute core (deriveFlags, buildMasterRows + helpers) is byte-exact to
 * flag_logic.py / data_access.py and validated by .kmc_validation parity tests.
 */

// ====================== constants ======================
var THRESHOLDS = {
  visits: 3.0, mort_low: 0.02, mort_high: 0.20, enroll: 0.35,
  danger_high: 0.30, danger_zero: 0.0, wt_loss: 0.15, wt_gain: 60.0,
  wt_zero: 0.30, round_weight: 0.80, hr_copycat: 0.75, temp_copycat: 0.75,
  spo2_implausible: 0.10, ga_fullterm: 0.30, gps_same_case_far: 0.30, ds_no_referral: 0.0
};
var MIN_CASES = {
  visits: 10, mort: 20, enroll: 10, danger_high: 20, danger_zero: 30,
  weight: 10, exclude: 20, round_weight: 20, hr_copycat: 20, temp_copycat: 20,
  spo2_implausible: 20, ga_fullterm: 10, gps_same_case_far: 20, ds_no_referral: 5
};
var ALL_FLAGS = ["flag_visits","flag_mort_low","flag_mort_high","flag_enroll","flag_danger_high","flag_danger_zero","flag_wt_loss","flag_wt_gain","flag_wt_zero","flag_round_weight","flag_hr_copycat","flag_temp_copycat","flag_spo2_implausible","flag_ga_fullterm","flag_gps_same_case_far","flag_ds_no_referral"];
var PRIORITY_FLAGS = ["flag_visits","flag_mort","flag_enroll","flag_danger_high","flag_ds_no_referral","flag_round_weight","flag_hr_copycat","flag_temp_copycat","flag_spo2_implausible","flag_gps_same_case_far"];
var SECONDARY_FLAGS = ["flag_mort_low","flag_mort_high","flag_danger_zero","flag_wt_loss","flag_wt_gain","flag_wt_zero","flag_ga_fullterm"];
var FLAG_LABELS = {flag_visits:"Visits/Case",flag_mort:"Mortality",flag_mort_low:"Low Mortality",flag_mort_high:"High Mortality",flag_enroll:"Late Enrollment",flag_danger_high:"Danger Signs",flag_danger_zero:"No Danger Signs",flag_wt_loss:"Weight Loss",flag_wt_gain:"Weight Gain",flag_wt_zero:"Weight Stagnant",flag_round_weight:"Rounded Weights",flag_hr_copycat:"HR Copy-Paste",flag_temp_copycat:"Temp Copy-Paste",flag_spo2_implausible:"SpO2 Implausible",flag_ga_fullterm:"Gestational Age",flag_gps_same_case_far:"GPS Spread",flag_ds_no_referral:"No Referral"};
var FLAG_THRESHOLD_DISPLAY = {flag_visits:"< 3.0",flag_mort:"< 2% or > 20%",flag_mort_low:"< 2%",flag_mort_high:"> 20%",flag_enroll:"> 35%",flag_danger_high:"> 30%",flag_danger_zero:"= 0%",flag_wt_loss:"> 15%",flag_wt_gain:"> 60 g/d",flag_wt_zero:"> 30%",flag_round_weight:">= 80%",flag_hr_copycat:"> 75%",flag_temp_copycat:"> 75%",flag_spo2_implausible:"> 10%",flag_ga_fullterm:"> 30%",flag_gps_same_case_far:"> 30%",flag_ds_no_referral:"= 0%"};
var FLAG_METRIC_KEY = {flag_visits:"avg_visits",flag_mort:"mort_rate",flag_mort_low:"mort_rate",flag_mort_high:"mort_rate",flag_enroll:"pct_late_enroll",flag_danger_high:"danger_rate",flag_danger_zero:"danger_rate",flag_wt_loss:"pct_wt_loss",flag_wt_gain:"mean_daily_gain",flag_wt_zero:"pct_wt_zero",flag_round_weight:"round_weight_pct",flag_hr_copycat:"hr_copycat_pct",flag_temp_copycat:"temp_copycat_pct",flag_spo2_implausible:"spo2_implausible_pct",flag_ga_fullterm:"ga_fullterm_pct",flag_gps_same_case_far:"gps_same_case_far_pct",flag_ds_no_referral:"ds_no_referral_pct"};
var FLAG_FMT = {flag_visits:"dec",flag_mort:"pct",flag_mort_low:"pct",flag_mort_high:"pct",flag_enroll:"pct",flag_danger_high:"pct",flag_danger_zero:"pct",flag_wt_loss:"pct",flag_wt_gain:"gain",flag_wt_zero:"pct",flag_round_weight:"pct",flag_hr_copycat:"pct",flag_temp_copycat:"pct",flag_spo2_implausible:"pct",flag_ga_fullterm:"pct",flag_gps_same_case_far:"pct",flag_ds_no_referral:"pct"};
var FLAG_DESCRIPTIONS = {flag_visits:"Avg follow-up visits per closed non-mortality case < 3.0 (min 10 cases).",flag_mort:"Mortality < 2% (implausible) or > 20% (concern). Min 20 closed cases.",flag_enroll:"> 35% of cases enrolled 8+ days after discharge. Min 10 cases w/ dates.",flag_danger_high:"> 30% of follow-up visits show danger signs. Min 20 visits.",flag_danger_zero:"Exactly 0% danger signs across 30+ visits.",flag_wt_loss:"> 15% of successive weight pairs show loss. Min 10 pairs.",flag_wt_gain:"Avg daily weight gain per baby > 60 g/day. Per-baby averaging.",flag_wt_zero:"> 30% of successive weight pairs show no change. Min 10 pairs.",flag_round_weight:">= 80% of follow-up weights are exact multiples of 100g. Min 20.",flag_hr_copycat:"> 75% of heart-rate readings are the same value. Min 20.",flag_temp_copycat:"> 75% of temperature readings are the same value. Min 20.",flag_spo2_implausible:"> 10% of SpO2 readings outside 70-100%. Min 20.",flag_ga_fullterm:"> 30% of registrations with gestational age >= 37 weeks. Min 10.",flag_gps_same_case_far:"> 30% of same-case GPS pairs > 1km apart. Min 20.",flag_ds_no_referral:"0% referral rate for danger-sign-positive visits. Min 5 DS+ visits.",flag_mort_low:"Mortality < 2% — implausible. Min 20.",flag_mort_high:"Mortality > 20% — concern. Min 20."};
var OPP_META = {523:{llo:"NAMA",name:"Nama Wellness- KMC"},524:{llo:"PIPN",name:"PIPN (V1)"},675:{llo:"GHI",name:"GHI"},874:{llo:"PIPN",name:"KMC PIPN - New Opportunity (V2)"},938:{llo:"NAMA",name:"KMC Nama - New Opportunity (V2)"}};

// ====================== compute core (validated; re-run parity before editing) ======================
var CLOSED_STATUSES = {discharged:1,lost_to_followup:1,deceased:1};
var DECEASED_STATUS = "deceased";
var WEIGHT_MIN_G = 500, WEIGHT_MAX_G = 5000, KG_TO_G = 1000;
var PAIR_MIN_DAYS = 1, PAIR_MAX_DAYS = 30, LATE_ENROLL_DAYS = 8;
var SPO2_MIN = 70, SPO2_MAX = 100, GA_FULLTERM_WEEKS = 37, EARTH_RADIUS_KM = 6371.0;
var YES_SET = {"yes":1,"true":1,"1":1};

function rget(row, key) { if (row == null) return null; var v = row[key]; return v === undefined ? null : v; }
function parseDate(value) {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value !== "string") { if (value instanceof Date) return Date.UTC(value.getUTCFullYear(), value.getUTCMonth(), value.getUTCDate()); return null; }
  var s = value.slice(0,10); var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return null; return Date.UTC(parseInt(m[1],10), parseInt(m[2],10)-1, parseInt(m[3],10));
}
function daysBetween(a, b) { return Math.round((b - a) / 86400000); }
function safeFloat(value) { if (value === null || value === undefined || value === "" || typeof value === "boolean") return null; var f = Number(value); return isNaN(f) ? null : f; }
function safeInt(value) { if (value === null || value === undefined || value === "") return 0; var f = Number(value); return isNaN(f) ? 0 : Math.trunc(f); }
function readWeightG(row) { var w = safeFloat(rget(row,"weight")); if (w === null || w <= 0) return null; if (w < 50) return w*KG_TO_G; if (w >= 100 && w <= 10000) return w; return null; }
function stableSort(arr, keyFn) { return arr.map(function(v,i){return {v:v,i:i,k:keyFn(v)};}).sort(function(a,b){return a.k<b.k?-1:a.k>b.k?1:a.i-b.i;}).map(function(x){return x.v;}); }
function inYes(v){ if (v===true||v===1) return true; if (typeof v==="string") return !!YES_SET[v.toLowerCase()]; return false; }
function inNo(v){ if (v===false||v===0) return true; if (typeof v==="string"){var s=v.toLowerCase(); return s==="no"||s==="false"||s==="0";} return false; }

function computeWeightMetrics(visitRows) {
  var byChild = {}, i, row, cid;
  for (i=0;i<visitRows.length;i++){ row=visitRows[i]; cid=rget(row,"beneficiary_case_id"); if(!cid)continue; cid=String(cid); (byChild[cid]=byChild[cid]||[]).push(row); }
  var totalPairs=0, lossPairs=0, zeroPairs=0, gainPairCount=0, babyAvgGains=[];
  Object.keys(byChild).forEach(function(k){
    var visits=byChild[k], eligible=[];
    for (var j=0;j<visits.length;j++){ if (readWeightG(visits[j])!==null && parseDate(rget(visits[j],"visit_date"))!==null) eligible.push(visits[j]); }
    eligible = stableSort(eligible, function(v){ return parseDate(rget(v,"visit_date")); });
    var childGains=[];
    for (var p=1;p<eligible.length;p++){
      var prevW=readWeightG(eligible[p-1]), currW=readWeightG(eligible[p]);
      if (prevW===null||currW===null) continue;
      if (!(prevW>=WEIGHT_MIN_G && prevW<=WEIGHT_MAX_G)) continue;
      if (!(currW>=WEIGHT_MIN_G && currW<=WEIGHT_MAX_G)) continue;
      var db=daysBetween(parseDate(rget(eligible[p-1],"visit_date")), parseDate(rget(eligible[p],"visit_date")));
      if (db<PAIR_MIN_DAYS||db>PAIR_MAX_DAYS) continue;
      totalPairs++; var diff=currW-prevW;
      if (diff<0) lossPairs++;
      if (Math.abs(diff)<0.001) zeroPairs++;
      if (diff>0 && db>0){ childGains.push(diff/db); gainPairCount++; }
    }
    if (childGains.length){ var s=0; for(var g=0;g<childGains.length;g++) s+=childGains[g]; babyAvgGains.push(s/childGains.length); }
  });
  var meanGain=null; if (babyAvgGains.length){ var ss=0; for(var b=0;b<babyAvgGains.length;b++) ss+=babyAvgGains[b]; meanGain=ss/babyAvgGains.length; }
  return { pct_wt_loss: totalPairs>0?lossPairs/totalPairs:null, mean_daily_gain: meanGain, pct_wt_zero: totalPairs>0?zeroPairs/totalPairs:null, weight_pairs: totalPairs, gain_pairs: gainPairCount };
}
function computeEnrollmentMetrics(visitRows) {
  var byCase={}, i, row, cid;
  for (i=0;i<visitRows.length;i++){ row=visitRows[i]; cid=rget(row,"beneficiary_case_id"); if(!cid)continue; cid=String(cid);
    var slot=byCase[cid]||(byCase[cid]={reg_date:null,discharge_date:null});
    var rd=parseDate(rget(row,"reg_date")), dd=parseDate(rget(row,"discharge_date"));
    if (rd!==null && slot.reg_date===null) slot.reg_date=rd;
    if (dd!==null && slot.discharge_date===null) slot.discharge_date=dd;
  }
  var casesWithDates=0, lateCases=0;
  Object.keys(byCase).forEach(function(k){ var s=byCase[k]; if (s.reg_date!==null && s.discharge_date!==null){ casesWithDates++; if (daysBetween(s.discharge_date,s.reg_date)>=LATE_ENROLL_DAYS) lateCases++; } });
  return { pct_late_enroll: casesWithDates>=MIN_CASES.enroll?lateCases/casesWithDates:null, cases_with_dates: casesWithDates };
}
function computeCaseMetrics(visitRows) {
  var byCase={}, i, row, cid;
  for (i=0;i<visitRows.length;i++){ row=visitRows[i]; cid=rget(row,"beneficiary_case_id"); if(!cid)continue; cid=String(cid);
    var slot=byCase[cid]||(byCase[cid]={case_id:cid,latest_visit_date:null,latest_status:null,latest_child_alive:null,visit_count:0});
    if (rget(row,"visit_number")!==null && rget(row,"visit_number")!==undefined) slot.visit_count++;
    var vdate=parseDate(rget(row,"visit_date")); if (vdate===null) continue;
    if (slot.latest_visit_date===null || vdate>slot.latest_visit_date){
      slot.latest_visit_date=vdate;
      var status=rget(row,"kmc_status"); if (status){ var st=String(status).trim().toLowerCase(); slot.latest_status=st||null; }
      var ca=rget(row,"child_alive"); if (ca!==null&&ca!==undefined){ var cl=String(ca).trim().toLowerCase(); slot.latest_child_alive=cl||null; }
    }
  }
  var cases=Object.keys(byCase).map(function(k){return byCase[k];});
  function isClosed(c){ return !!CLOSED_STATUSES[c.latest_status] || c.latest_child_alive==="no"; }
  function isMortality(c){ if (c.latest_child_alive==="no") return true; if (c.latest_child_alive==="yes") return false; return c.latest_status===DECEASED_STATUS; }
  var closed=cases.filter(isClosed), closedCases=closed.length, nonMortClosed=0;
  for (i=0;i<closed.length;i++) if (!isMortality(closed[i])) nonMortClosed++;
  var deaths=0; for (i=0;i<cases.length;i++) if (isMortality(cases[i])) deaths++;
  return { cases:cases, closed_cases:closedCases, non_mort_closed:nonMortClosed, deaths:deaths, is_closed:isClosed, is_mortality:isMortality };
}
function computeAvgVisits(cm){ var nmc=cm.cases.filter(function(c){return cm.is_closed(c)&&!cm.is_mortality(c);}); if (nmc.length<MIN_CASES.visits) return [null,nmc.length]; var t=0; for(var i=0;i<nmc.length;i++) t+=nmc[i].visit_count; return [t/nmc.length, nmc.length]; }
function computeRoundWeightPct(visitRows){ var valid=[]; for(var i=0;i<visitRows.length;i++){ if (rget(visitRows[i],"visit_number")===null||rget(visitRows[i],"visit_number")===undefined) continue; var w=readWeightG(visitRows[i]); if (w===null) continue; if (!(w>=WEIGHT_MIN_G&&w<=WEIGHT_MAX_G)) continue; valid.push(w);} if (valid.length<MIN_CASES.round_weight) return [null,valid.length]; var r=0; for(var j=0;j<valid.length;j++) if (Math.abs(valid[j]-Math.round(valid[j]/100)*100)<0.001) r++; return [r/valid.length, valid.length]; }
function copycatPct(visitRows, field, minKey){ var vals=[]; for(var i=0;i<visitRows.length;i++){ var x=safeFloat(rget(visitRows[i],field)); if (x!==null) vals.push(x);} if (vals.length<MIN_CASES[minKey]) return [null,vals.length]; var counts={}, top=0; for(var j=0;j<vals.length;j++){ var key=String(vals[j]); counts[key]=(counts[key]||0)+1; if (counts[key]>top) top=counts[key];} return [top/vals.length, vals.length]; }
function computeSpo2ImplausiblePct(visitRows){ var vals=[]; for(var i=0;i<visitRows.length;i++){ var v=safeFloat(rget(visitRows[i],"spo2_level")); if (v!==null) vals.push(v);} if (vals.length<MIN_CASES.spo2_implausible) return [null,vals.length]; var bad=0; for(var j=0;j<vals.length;j++) if (vals[j]<SPO2_MIN||vals[j]>SPO2_MAX) bad++; return [bad/vals.length, vals.length]; }
function computeGaFulltermPct(visitRows){ var vals=[]; for(var i=0;i<visitRows.length;i++){ var ga=safeFloat(rget(visitRows[i],"gestational_age_lmp")); if (ga!==null) vals.push(ga);} if (vals.length<MIN_CASES.ga_fullterm) return [null,vals.length]; var ft=0; for(var j=0;j<vals.length;j++) if (vals[j]>=GA_FULLTERM_WEEKS) ft++; return [ft/vals.length, vals.length]; }
function parseGps(raw){ if (!raw||typeof raw!=="string") return null; var p=raw.trim().split(/\s+/); if (p.length<2) return null; var lat=Number(p[0]), lon=Number(p[1]); if (isNaN(lat)||isNaN(lon)) return null; if (!(lat>=-90&&lat<=90&&lon>=-180&&lon<=180)) return null; if (lat===0.0&&lon===0.0) return null; return [lat,lon]; }
function haversineKm(la1,lo1,la2,lo2){ var dlat=(la2-la1)*Math.PI/180, dlon=(lo2-lo1)*Math.PI/180; var a=Math.sin(dlat/2)*Math.sin(dlat/2)+Math.cos(la1*Math.PI/180)*Math.cos(la2*Math.PI/180)*Math.sin(dlon/2)*Math.sin(dlon/2); return EARTH_RADIUS_KM*2*Math.atan2(Math.sqrt(a),Math.sqrt(1-a)); }
function computeGpsSameCaseFarPct(visitRows){ var cases={}; for(var i=0;i<visitRows.length;i++){ var cid=rget(visitRows[i],"beneficiary_case_id"); if(!cid)continue; var c=parseGps(rget(visitRows[i],"gps")); if (c===null) continue; (cases[String(cid)]=cases[String(cid)]||[]).push(c);} var total=0, far=0; Object.keys(cases).forEach(function(k){ var pts=cases[k]; if (pts.length<2) return; for(var j=0;j<pts.length-1;j++){ total++; if (haversineKm(pts[j][0],pts[j][1],pts[j+1][0],pts[j+1][1])>1.0) far++; } }); if (total<MIN_CASES.gps_same_case_far) return [null,total]; return [far/total,total]; }
function computeDsNoReferralPct(visitRows){ var ds=[]; for(var i=0;i<visitRows.length;i++){ var d=rget(visitRows[i],"danger_sign_positive"); if (inYes(d)){ ds.push(inYes(rget(visitRows[i],"child_referred"))); } } if (ds.length<MIN_CASES.ds_no_referral) return [null,ds.length]; var ref=0; for(var j=0;j<ds.length;j++) if (ds[j]) ref++; return [ref/ds.length, ds.length]; }
function computeDangerMetrics(visitRows){ var vf=0, pv=0; for(var i=0;i<visitRows.length;i++){ var d=rget(visitRows[i],"danger_sign_positive"); if (inYes(d)){ vf++; pv++; } else if (inNo(d)){ vf++; } } return { danger_visit_count: vf, danger_positive_count: pv }; }

function deriveFlags(aggRow, visitRows) {
  var username=String(rget(aggRow,"username")||"");
  var totalCases=safeInt(rget(aggRow,"total_cases"));
  var totalVisits=safeInt(rget(aggRow,"kmc_visit_count"));
  var dvm=computeDangerMetrics(visitRows), dangerVisitCount, dangerPositiveCount;
  if (dvm.danger_visit_count>0){ dangerVisitCount=dvm.danger_visit_count; dangerPositiveCount=dvm.danger_positive_count; }
  else { dangerVisitCount=safeInt(rget(aggRow,"danger_visit_count")); dangerPositiveCount=safeInt(rget(aggRow,"danger_positive_count")); }
  var wm=computeWeightMetrics(visitRows), em=computeEnrollmentMetrics(visitRows), cm=computeCaseMetrics(visitRows);
  var closedCases=cm.closed_cases, nonMortClosed=cm.non_mort_closed, deaths=cm.deaths;
  var avgVisits=computeAvgVisits(cm)[0];
  var mortRate=closedCases>0?deaths/closedCases:null;
  var dangerRate=dangerVisitCount>0?dangerPositiveCount/dangerVisitCount:null;
  var roundPct=computeRoundWeightPct(visitRows)[0];
  var hrPct=copycatPct(visitRows,"heart_rate","hr_copycat")[0];
  var tempPct=copycatPct(visitRows,"temperature","temp_copycat")[0];
  var spo2Pct=computeSpo2ImplausiblePct(visitRows)[0];
  var gaPct=computeGaFulltermPct(visitRows)[0];
  var gpsPct=computeGpsSameCaseFarPct(visitRows)[0];
  var referralPct=computeDsNoReferralPct(visitRows)[0];
  var excluded=totalCases<MIN_CASES.exclude;
  var flags={}; for (var fi=0;fi<ALL_FLAGS.length;fi++) flags[ALL_FLAGS[fi]]=null;
  if (!excluded){
    flags.flag_visits = avgVisits!==null ? (avgVisits<THRESHOLDS.visits) : null;
    flags.flag_mort_high = (closedCases>=MIN_CASES.mort && mortRate!==null) ? (mortRate>THRESHOLDS.mort_high) : null;
    flags.flag_mort_low = (closedCases>=MIN_CASES.mort && mortRate!==null) ? (mortRate<THRESHOLDS.mort_low) : null;
    flags.flag_enroll = (em.cases_with_dates>=MIN_CASES.enroll && em.pct_late_enroll!==null) ? (em.pct_late_enroll>THRESHOLDS.enroll) : null;
    flags.flag_danger_high = (dangerVisitCount>=MIN_CASES.danger_high && dangerRate!==null) ? (dangerRate>THRESHOLDS.danger_high) : null;
    flags.flag_danger_zero = (dangerVisitCount>=MIN_CASES.danger_zero && dangerRate!==null) ? (dangerRate===THRESHOLDS.danger_zero) : null;
    flags.flag_wt_loss = (wm.weight_pairs>=MIN_CASES.weight && wm.pct_wt_loss!==null) ? (wm.pct_wt_loss>THRESHOLDS.wt_loss) : null;
    flags.flag_wt_gain = wm.mean_daily_gain!==null ? (wm.mean_daily_gain>THRESHOLDS.wt_gain) : null;
    flags.flag_wt_zero = (wm.weight_pairs>=MIN_CASES.weight && wm.pct_wt_zero!==null) ? (wm.pct_wt_zero>THRESHOLDS.wt_zero) : null;
    flags.flag_round_weight = roundPct!==null ? (roundPct>=THRESHOLDS.round_weight) : null;
    flags.flag_hr_copycat = hrPct!==null ? (hrPct>THRESHOLDS.hr_copycat) : null;
    flags.flag_temp_copycat = tempPct!==null ? (tempPct>THRESHOLDS.temp_copycat) : null;
    flags.flag_spo2_implausible = spo2Pct!==null ? (spo2Pct>THRESHOLDS.spo2_implausible) : null;
    flags.flag_ga_fullterm = gaPct!==null ? (gaPct>THRESHOLDS.ga_fullterm) : null;
    flags.flag_gps_same_case_far = gpsPct!==null ? (gpsPct>THRESHOLDS.gps_same_case_far) : null;
    flags.flag_ds_no_referral = referralPct!==null ? (referralPct===THRESHOLDS.ds_no_referral) : null;
  }
  var ml=flags.flag_mort_low, mh=flags.flag_mort_high;
  if (excluded || (ml===null && mh===null)) flags.flag_mort=null; else flags.flag_mort=(!!ml)||(!!mh);
  return { username:username, total_cases:totalCases, total_visits:totalVisits, deaths:deaths, closed_cases:closedCases, non_mort_closed:nonMortClosed, avg_visits:avgVisits, mort_rate:mortRate, danger_rate:dangerRate, pct_late_enroll:em.pct_late_enroll, cases_with_dates:em.cases_with_dates, pct_wt_loss:wm.pct_wt_loss, mean_daily_gain:wm.mean_daily_gain, pct_wt_zero:wm.pct_wt_zero, weight_pairs:wm.weight_pairs, round_weight_pct:roundPct, hr_copycat_pct:hrPct, temp_copycat_pct:tempPct, spo2_implausible_pct:spo2Pct, ga_fullterm_pct:gaPct, gps_same_case_far_pct:gpsPct, ds_no_referral_pct:referralPct, excluded:excluded, flags:flags };
}
function lloFor(oppId){ var m=OPP_META[oppId]; return m?m.llo:("opp_"+oppId); }
function buildMasterRows(flwRows, visitRows, nameByUser) {
  nameByUser=nameByUser||{};
  var visitsByOppUser={}, i, r, k;
  for (i=0;i<visitRows.length;i++){ r=visitRows[i]; k=r.opportunity_id+"|"+r.username; (visitsByOppUser[k]=visitsByOppUser[k]||[]).push(r); }
  var buckets={};
  var sorted=flwRows.slice().sort(function(a,b){return (a.opportunity_id||0)-(b.opportunity_id||0);});
  for (i=0;i<sorted.length;i++){ r=sorted[i]; var uname=r.username; if(!uname)continue; var llo=lloFor(r.opportunity_id); var bkey=llo+"|"+uname;
    var b=buckets[bkey]; if(!b){ b=buckets[bkey]={username:uname,llo:llo,flw_name:null,agg_total_cases:0,agg_kmc_visit_count:0,agg_danger_visit_count:0,agg_danger_positive_count:0,visit_rows:[],opportunity_ids:[],opportunity_breakdown:[]}; }
    if (!b.flw_name) b.flw_name=nameByUser[uname]||r.flw_name||null;
    var oc=parseInt(r.total_cases,10)||0, ov=parseInt(r.kmc_visit_count,10)||0, odv=parseInt(r.danger_visit_count,10)||0, odp=parseInt(r.danger_positive_count,10)||0;
    b.agg_total_cases+=oc; b.agg_kmc_visit_count+=ov; b.agg_danger_visit_count+=odv; b.agg_danger_positive_count+=odp;
    var vs=visitsByOppUser[r.opportunity_id+"|"+uname]||[]; for (var j=0;j<vs.length;j++) b.visit_rows.push(vs[j]);
    b.opportunity_ids.push(r.opportunity_id);
    b.opportunity_breakdown.push({opportunity_id:r.opportunity_id,name:(OPP_META[r.opportunity_id]||{}).name||("Opp "+r.opportunity_id),total_cases:oc,kmc_visit_count:ov});
  }
  var out=[];
  Object.keys(buckets).forEach(function(bk){ var b=buckets[bk];
    var aggDict={username:b.username,flw_name:b.flw_name,total_cases:b.agg_total_cases,kmc_visit_count:b.agg_kmc_visit_count,danger_visit_count:b.agg_danger_visit_count,danger_positive_count:b.agg_danger_positive_count};
    var res=deriveFlags(aggDict,b.visit_rows);
    res.flw_name=b.flw_name||b.username; res.llo=b.llo; res.opportunity_ids=b.opportunity_ids.slice(); res.opportunity_breakdown=b.opportunity_breakdown.slice();
    res.primary_opp=b.opportunity_ids.length?Math.max.apply(null,b.opportunity_ids):null; res._visit_rows=b.visit_rows;
    res.priority_flag_count=PRIORITY_FLAGS.filter(function(f){return res.flags[f]===true;}).length;
    res.flag_count=ALL_FLAGS.filter(function(f){return res.flags[f]===true;}).length;
    out.push(res);
  });
  return out;
}
function fmtVal(val, type){ if (val===null||val===undefined) return null; if (type==="pct") return (val*100).toFixed(1)+"%"; if (type==="dec") return val.toFixed(1); if (type==="gain") return val.toFixed(1)+" g/d"; return String(val); }

// ====================== UI ======================
function WorkflowUI({ definition, instance, workers, pipelines, links, actions, onUpdateState }) {
  var h = React.createElement;
  var flwRows = (pipelines && pipelines.flw_flags && pipelines.flw_flags.rows) || [];
  var visitRows = (pipelines && pipelines.weight_series && pipelines.weight_series.rows) || [];

  var nameByUser = React.useMemo(function(){ var m={}; (workers||[]).forEach(function(w){ if (w && w.username && w.name) m[w.username]=w.name; }); return m; }, [workers]);
  var masterRows = React.useMemo(function(){ return buildMasterRows(flwRows, visitRows, nameByUser); }, [flwRows, visitRows, nameByUser]);

  var _filter = React.useState("all"); var filter=_filter[0], setFilter=_filter[1];
  var _llo = React.useState("all"); var lloFilter=_llo[0], setLloFilter=_llo[1];
  var _search = React.useState(""); var search=_search[0], setSearch=_search[1];
  var _sortKey = React.useState("priority"); var sortKey=_sortKey[0], setSortKey=_sortKey[1];
  var _sortAsc = React.useState(false); var sortAsc=_sortAsc[0], setSortAsc=_sortAsc[1];
  var _showSec = React.useState(false); var showSecondary=_showSec[0], setShowSecondary=_showSec[1];
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
    var loaded=masterRows.length, excluded=0, priority=0, anyf=0, totalVisits=0, totalCases=0;
    masterRows.forEach(function(r){ if (r.excluded) excluded++; if (r.priority_flag_count>=1) priority++; if (r.flag_count>=1) anyf++; totalVisits+=r.total_visits||0; totalCases+=r.total_cases||0; });
    return { loaded:loaded, excluded:excluded, priority:priority, anyf:anyf, totalVisits:totalVisits, totalCases:totalCases };
  }, [masterRows]);

  var analyzed = masterRows.filter(function(r){ return !r.excluded; });
  var filtered = React.useMemo(function(){
    var data = analyzed.slice();
    if (lloFilter!=="all") data=data.filter(function(d){return d.llo===lloFilter;});
    if (search.trim()){ var q=search.toLowerCase(); data=data.filter(function(d){ return (d.username&&d.username.toLowerCase().indexOf(q)>=0)||(d.flw_name&&d.flw_name.toLowerCase().indexOf(q)>=0); }); }
    if (filter==="priority") data=data.filter(function(d){return d.priority_flag_count>=1;});
    else if (filter==="any") data=data.filter(function(d){return d.flag_count>=1;});
    else if (filter==="two_plus") data=data.filter(function(d){return d.flag_count>=2;});
    data.sort(function(a,b){
      var va, vb;
      if (sortKey==="name"){ va=a.flw_name||a.username||""; vb=b.flw_name||b.username||""; var c=va.localeCompare(vb); return sortAsc?c:-c; }
      if (sortKey==="cases"){ va=a.total_cases; vb=b.total_cases; }
      else if (sortKey==="priority"){ va=a.priority_flag_count; vb=b.priority_flag_count; }
      else if (sortKey==="flags"){ va=a.flag_count; vb=b.flag_count; }
      else { var mk=FLAG_METRIC_KEY[sortKey]; va=(a[mk]==null?-1:a[mk]); vb=(b[mk]==null?-1:b[mk]); }
      return sortAsc?va-vb:vb-va;
    });
    return data;
  }, [analyzed, filter, lloFilter, search, sortKey, sortAsc]);

  var selectedRows = filtered.filter(function(d){ return selected[d.llo+"|"+d.username]; });
  var selectedCount = selectedRows.length;
  function toggleSort(kk){ if (sortKey===kk) setSortAsc(!sortAsc); else { setSortKey(kk); setSortAsc(false); } }
  function rowKey(d){ return d.llo+"|"+d.username; }
  function toggleSelect(d){ setSelected(function(prev){ var n=Object.assign({},prev); var kk=rowKey(d); n[kk]=!prev[kk]; return n; }); }
  function SortArrow(kk){ if (sortKey!==kk) return null; return h("span",{className:"ml-1 text-xs"}, sortAsc?"▲":"▼"); }
  var thBase="px-2 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none whitespace-nowrap";

  function metricCell(d, flag){
    var val=d[FLAG_METRIC_KEY[flag]]; var state=d.flags[flag]; var formatted=fmtVal(val, FLAG_FMT[flag]);
    var flagged=state===true; var amber=(flag==="flag_danger_zero"||flag==="flag_ds_no_referral")&&flagged;
    var cls="px-2 py-2 text-sm text-center whitespace-nowrap "+(flagged?(amber?"bg-amber-50 text-amber-800 font-semibold":"bg-red-50 text-red-800 font-semibold"):"");
    if (state===null || formatted===null) return h("td",{className:cls,key:flag,title:"Not eligible — insufficient data"}, h("span",{className:"text-gray-400 italic"},"NE"));
    if (flagged) return h("td",{className:cls,key:flag,title:FLAG_LABELS[flag]+" "+FLAG_THRESHOLD_DISPLAY[flag]}, formatted);
    return h("td",{className:cls,key:flag}, formatted, h("span",{className:"ml-1 text-green-500 text-xs"},"✓"));
  }

  function detailPanel(d){
    var metrics=[["Total cases",d.total_cases],["Closed",d.closed_cases],["Deaths",d.deaths],["Non-mort closed",d.non_mort_closed],["Avg visits/case",fmtVal(d.avg_visits,"dec")],["Mortality",fmtVal(d.mort_rate,"pct")],["Danger rate",fmtVal(d.danger_rate,"pct")],["Late enroll",fmtVal(d.pct_late_enroll,"pct")],["Weight pairs",d.weight_pairs],["Wt loss",fmtVal(d.pct_wt_loss,"pct")],["Daily gain",fmtVal(d.mean_daily_gain,"gain")],["Wt zero",fmtVal(d.pct_wt_zero,"pct")]];
    var visits=(d._visit_rows||[]).slice().sort(function(a,b){var x=parseDate(rget(a,"visit_date"))||0, y=parseDate(rget(b,"visit_date"))||0; return y-x;}).slice(0,20);
    return h("div",{className:"space-y-4"},
      h("div",null,
        h("div",{className:"text-sm font-semibold text-gray-700 mb-2"}, "Opportunity breakdown"),
        h("div",{className:"flex flex-wrap gap-2"}, d.opportunity_breakdown.map(function(b){ return h("span",{key:b.opportunity_id, className:"text-xs bg-white border border-gray-200 rounded px-2 py-1"}, b.name+" — "+b.total_cases+" cases / "+b.kmc_visit_count+" visits"); }))),
      h("div",null,
        h("div",{className:"text-sm font-semibold text-gray-700 mb-2"}, "Metrics"),
        h("div",{className:"grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2"}, metrics.map(function(m){ return h("div",{key:m[0], className:"bg-white rounded border border-gray-200 p-2"}, h("div",{className:"text-xs text-gray-500"}, m[0]), h("div",{className:"text-sm font-medium text-gray-900"}, m[1]===null?"NE":m[1])); }))),
      h("div",null,
        h("div",{className:"text-sm font-semibold text-gray-700 mb-2"}, "All 16 flags"),
        h("div",{className:"flex flex-wrap gap-1"}, ALL_FLAGS.map(function(f){ var s=d.flags[f]; var cls=s===true?"bg-red-100 text-red-700":s===false?"bg-green-50 text-green-700":"bg-gray-100 text-gray-400"; return h("span",{key:f, className:"text-xs rounded px-2 py-0.5 "+cls, title:FLAG_DESCRIPTIONS[f]}, FLAG_LABELS[f]+(s===true?" ⚑":s===false?" ✓":" —")); }))),
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
      var criteria={ audit_type:"date_range", granularity:"per_flw", title:("KMC Flag Audit "+startDate+" to "+endDate), start_date:startDate, end_date:endDate, count_per_flw:countPerFlw,
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
      h("div",{className:"bg-gray-50 border border-gray-200 rounded-lg p-8 text-center text-gray-500"}, "No pipeline data yet — run the pipeline to load FLW flag metrics."));
  }

  // ---- header ----
  var headerEl = h("div",{className:"bg-white rounded-lg shadow-sm p-5"},
    h("h1",{className:"text-2xl font-bold text-gray-900"}, h("i",{className:"fa-solid fa-flag text-red-500 mr-2"}), definition.name),
    h("p",{className:"text-gray-600 mt-1"}, "16-flag KMC audit across merged V1+V2 opportunities. Live data."));

  // ---- KPIs ----
  var kpiDefs=[["FLWs Loaded", kpi.loaded, "blue"],["Priority Flags", kpi.priority, "red"],["Any Flags", kpi.anyf, "orange"],["Excluded (<20)", kpi.excluded, "gray"],["KMC Visits", kpi.totalVisits.toLocaleString(), "green"],["Total Cases", kpi.totalCases.toLocaleString(), "teal"]];
  var kpiEl = h("div",{className:"grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3"}, kpiDefs.map(function(c){
    return h("div",{key:c[0], className:"bg-white rounded-lg shadow-sm p-4 border-l-4 border-"+c[2]+"-500"}, h("div",{className:"text-2xl font-bold text-gray-900"}, c[1]), h("div",{className:"text-xs text-gray-600 mt-1"}, c[0]));
  }));

  // ---- filter bar ----
  var filterEl = h("div",{className:"bg-white rounded-lg shadow-sm p-3 flex flex-wrap items-center gap-3"},
    h("div",{className:"flex gap-2"}, [["all","All"],["priority","Priority"],["any","Any Flag"],["two_plus","2+ Flags"]].map(function(f){
      return h("button",{key:f[0], onClick:function(){setFilter(f[0]);}, className:"px-3 py-1.5 text-sm rounded-full border "+(filter===f[0]?"bg-blue-600 text-white border-blue-600":"bg-white text-gray-700 border-gray-300 hover:border-blue-400")}, f[1]);
    })),
    h("select",{value:lloFilter, onChange:function(e){setLloFilter(e.target.value);}, className:"border border-gray-300 rounded-lg px-2 py-1.5 text-sm"},
      h("option",{value:"all"},"All LLOs"), h("option",{value:"PIPN"},"PIPN"), h("option",{value:"NAMA"},"NAMA"), h("option",{value:"GHI"},"GHI")),
    h("input",{type:"text", placeholder:"Search FLW...", value:search, onChange:function(e){setSearch(e.target.value);}, className:"flex-1 min-w-40 border border-gray-300 rounded-lg px-3 py-1.5 text-sm"}),
    h("label",{className:"flex items-center gap-2 text-sm text-gray-700"}, h("input",{type:"checkbox", checked:showSecondary, onChange:function(e){setShowSecondary(e.target.checked);}}), "Show secondary flags"));

  // ---- table ----
  var headerCells=[ h("th",{key:"_chk", className:"px-2 py-3 w-8"}),
    h("th",{key:"_name", className:thBase+" text-left", onClick:function(){toggleSort("name");}}, "FLW", SortArrow("name")),
    h("th",{key:"_llo", className:thBase+" text-left"}, "LLO"),
    h("th",{key:"_cases", className:thBase+" text-center", onClick:function(){toggleSort("cases");}}, "Cases", SortArrow("cases")) ];
  PRIORITY_FLAGS.forEach(function(f){ headerCells.push(h("th",{key:f, className:thBase+" text-center", onClick:function(){toggleSort(f);}, title:FLAG_DESCRIPTIONS[f]}, FLAG_LABELS[f], SortArrow(f))); });
  if (showSecondary) SECONDARY_FLAGS.forEach(function(f){ headerCells.push(h("th",{key:f, className:thBase+" text-center bg-gray-100", onClick:function(){toggleSort(f);}, title:FLAG_DESCRIPTIONS[f]}, FLAG_LABELS[f], SortArrow(f))); });
  headerCells.push(h("th",{key:"_flags", className:thBase+" text-center", onClick:function(){toggleSort("flags");}}, "Flags", SortArrow("flags")));

  var bodyRows=[];
  filtered.forEach(function(d){
    var kk=rowKey(d);
    var border=d.priority_flag_count>=2?"border-l-4 border-red-500":d.priority_flag_count===1?"border-l-4 border-orange-400":"";
    var cells=[ h("td",{key:"_chk", className:"px-2 py-2 text-center"}, h("input",{type:"checkbox", checked:!!selected[kk], onChange:function(){toggleSelect(d);}, disabled:isRunning})),
      h("td",{key:"_name", className:"px-2 py-2 text-sm cursor-pointer", onClick:function(){setExpanded(expanded===kk?null:kk);}},
        h("div",{className:"font-medium text-gray-900 flex items-center gap-1"}, h("i",{className:"fa-solid "+(expanded===kk?"fa-caret-down":"fa-caret-right")+" text-gray-400"}), d.flw_name),
        (d.flw_name!==d.username)?h("div",{className:"text-xs text-gray-400 font-mono"}, d.username):null),
      h("td",{key:"_llo", className:"px-2 py-2 text-sm"}, h("span",{className:"px-2 py-0.5 rounded text-xs bg-indigo-50 text-indigo-700"}, d.llo)),
      h("td",{key:"_cases", className:"px-2 py-2 text-sm text-center", title:d.opportunity_breakdown.map(function(b){return b.name+": "+b.total_cases+" cases";}).join(" | ")}, d.total_cases) ];
    PRIORITY_FLAGS.forEach(function(f){ cells.push(metricCell(d,f)); });
    if (showSecondary) SECONDARY_FLAGS.forEach(function(f){ cells.push(metricCell(d,f)); });
    cells.push(h("td",{key:"_flags", className:"px-2 py-2 text-center"},
      d.flag_count>0 ? h("span",{className:"inline-flex items-center justify-center w-7 h-7 rounded-full text-white text-xs font-bold "+(d.priority_flag_count>=2?"bg-red-500":d.priority_flag_count===1?"bg-orange-400":"bg-gray-400"), title:ALL_FLAGS.filter(function(x){return d.flags[x]===true;}).map(function(x){return FLAG_LABELS[x];}).join(", ")}, d.flag_count)
        : h("span",{className:"inline-flex items-center justify-center w-7 h-7 rounded-full bg-green-100 text-green-600 text-xs"}, "✓")));
    bodyRows.push(h("tr",{key:kk, className:(selected[kk]?"bg-blue-50 ":"hover:bg-gray-50 ")+border}, cells));
    if (expanded===kk){
      var colSpan=4+PRIORITY_FLAGS.length+(showSecondary?SECONDARY_FLAGS.length:0)+1;
      bodyRows.push(h("tr",{key:kk+"_d", className:"bg-gray-50"}, h("td",{colSpan:colSpan, className:"px-6 py-4"}, detailPanel(d))));
    }
  });

  var tableEl = h("div",{className:"bg-white rounded-lg shadow-sm overflow-x-auto"},
    h("table",{className:"min-w-full divide-y divide-gray-200"},
      h("thead",{className:"bg-gray-50"}, h("tr",null, headerCells)),
      h("tbody",{className:"bg-white divide-y divide-gray-200"}, bodyRows)),
    h("div",{className:"px-4 py-2 text-xs text-gray-500"}, filtered.length+" FLW"+(filtered.length!==1?"s":"")+" shown"));

  // ---- sticky action bar ----
  var progressEl = progress ? h("span",{className:"text-sm "+(progress.status==="failed"?"text-red-600":progress.status==="completed"?"text-green-600":"text-blue-600")},
    progress.status==="completed"?("✓ "+progress.message):progress.status==="failed"?("⚠ "+(progress.error||"Failed")):h("span",null, h("i",{className:"fa-solid fa-spinner fa-spin mr-1"}), progress.message)) : null;
  var actionBar = h("div",{className:"sticky bottom-0 bg-white border-t border-gray-200 shadow-lg p-3 -mx-4 sm:-mx-6 lg:-mx-8"},
    h("div",{className:"max-w-7xl mx-auto flex items-center justify-between gap-4"},
      h("div",{className:"flex items-center gap-4"}, h("span",{className:"text-sm text-gray-600"}, selectedCount+" FLW"+(selectedCount!==1?"s":"")+" selected"), progressEl),
      h("button",{onClick:function(){setShowModal(true);}, disabled:selectedCount===0||isRunning, className:"px-5 py-2.5 rounded-lg text-sm font-medium "+((selectedCount===0||isRunning)?"bg-gray-300 text-gray-500 cursor-not-allowed":"bg-red-600 text-white hover:bg-red-700")},
        isRunning?h("span",null,h("i",{className:"fa-solid fa-spinner fa-spin mr-2"}),"Creating..."):h("span",null,h("i",{className:"fa-solid fa-plus mr-2"}),"Create Audits ("+selectedCount+")"))));

  // ---- modal ----
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

  return h("div",{className:"space-y-5 pb-28"}, headerEl, kpiEl, filterEl, tableEl, actionBar, modal);
}
"""


TEMPLATE = {
    "key": "kmc_audit_dashboard",
    "name": "KMC Audit Dashboard",
    "description": (
        "16-flag KMC FLW audit across merged V1+V2 opportunities. "
        "Priority/secondary flag tiers, drilldown, one-click audit creation."
    ),
    "icon": "fa-flag",
    "color": "red",
    "multi_opp": True,
    "definition": DEFINITION,
    "render_code": RENDER_CODE,
    "pipeline_schemas": PIPELINE_SCHEMAS,
}
