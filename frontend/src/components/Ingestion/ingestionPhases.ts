export interface IngestionPhase {
  number:number;
  title:string;
  master:string;
}

// Presentation grouping of the production master pipeline's 12 numbered stages.
// The master's 2B/8B/9B/9C helper passes and final validation remain backend-internal;
// they are folded into the nearest primary phase here so the UI stays at x/12.
export const INGESTION_PHASES:IngestionPhase[]=[
  {number:1,title:"Plant collection",master:"STEP 1/10 - PLANT"},
  {number:2,title:"Plant-part collection",master:"STEP 2/10 - PLANT PART"},
  {number:3,title:"Build plant relationships",master:"STEP 3/10 - HAS_PART"},
  {number:4,title:"Map phytochemicals",master:"STEP 4/10 - PHYTOCHEMICAL MAPPING"},
  {number:5,title:"Collect compounds + build CONTAINS",master:"STEP 5A/10 + STEP 5B/10"},
  {number:6,title:"Collect bioactivity + link compounds",master:"STEP 6/10 + STEP 7/10"},
  {number:7,title:"Collect documents + REPORTED_IN",master:"STEP 8/10 - DOCUMENTS + REPORTED_IN"},
  {number:8,title:"Resolve targets + MEASURED_ON",master:"STEP 9/10 - TARGETS + UNIPROT + MEASURED_ON"},
  {number:9,title:"Normalize bioactivity nodes",master:"STEP 9C/12 - NORMALIZE BIOACTIVITY NODES"},
  {number:10,title:"Collect therapeutic uses",master:"STEP 10/12 - THERAPEUTIC USE COLLECTION"},
  {number:11,title:"Build therapeutic-use nodes",master:"STEP 11/12 - THERAPEUTIC USE BUILD"},
  {number:12,title:"Build USED_FOR relationships",master:"STEP 12/12 - USED_FOR"},
];
