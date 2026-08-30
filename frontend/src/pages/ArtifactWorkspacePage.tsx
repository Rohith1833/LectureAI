import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { listFinalizedVersions } from "@/services/knowledgeService";
import { artifactService } from "@/services/artifactService";
import type { KnowledgeVersion } from "@/types/knowledge";
import { ArtifactType, ArtifactStatus } from "@/types/artifact";
import type { ArtifactJobRead } from "@/types/artifact";

export default function ArtifactWorkspacePage() {
  const { id: uploadId } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [version, setVersion] = useState<KnowledgeVersion | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const [jobs, setJobs] = useState<ArtifactJobRead[]>([]);
  const [pollingJob, setPollingJob] = useState<string | null>(null);

  // Load the finalized knowledge version
  useEffect(() => {
    if (!uploadId) return;
    
    listFinalizedVersions(uploadId)
      .then((versions: KnowledgeVersion[]) => {
        if (versions.length > 0) {
          setVersion(versions[0]);
        } else {
          setError("No finalized knowledge version available for this document.");
        }
      })
      .catch((err: Error) => {
        console.error("Failed to load knowledge versions", err);
        setError("Failed to load knowledge versions.");
      })
      .finally(() => {
        setLoading(false);
      });
      
    // Load existing jobs
    loadJobs(uploadId);
  }, [uploadId]);
  
  const loadJobs = async (uid: string) => {
    try {
      const data = await artifactService.listJobs(uid);
      setJobs(data);
      // Check if any job is still pending/planning/rendering
      const activeJob = data.find(j => ([ArtifactStatus.PENDING, ArtifactStatus.PLANNING, ArtifactStatus.RENDERING] as ArtifactStatus[]).includes(j.status));
      if (activeJob) {
        setPollingJob(activeJob.id);
      }
    } catch (err) {
      console.error("Failed to load artifact jobs", err);
    }
  };

  // Poll for active job status
  useEffect(() => {
    if (!pollingJob) return;
    
    const interval = setInterval(async () => {
      try {
        const status = await artifactService.getJobStatus(pollingJob);
        setJobs(prev => prev.map(j => j.id === pollingJob ? status : j));
        
        if (([ArtifactStatus.COMPLETED, ArtifactStatus.FAILED] as ArtifactStatus[]).includes(status.status)) {
          setPollingJob(null);
        }
      } catch (err) {
        console.error("Failed to get job status", err);
        setPollingJob(null);
      }
    }, 2000);
    
    return () => clearInterval(interval);
  }, [pollingJob]);

  const handleGenerate = async () => {
    if (!uploadId || !version) return;
    
    try {
      const newJob = await artifactService.generateArtifact({
        upload_id: uploadId,
        knowledge_version_id: version.id,
        artifact_type: ArtifactType.PPTX,
        config: { num_units: 3 } // Example config
      });
      setJobs(prev => [newJob, ...prev]);
      setPollingJob(newJob.id);
    } catch (err: any) {
      setError(err.message || "Failed to start generation");
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-full p-8">
        <div className="animate-spin h-8 w-8 border-4 border-indigo-600 rounded-full border-t-transparent"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-lg">
          <p className="font-semibold">Error</p>
          <p>{error}</p>
          <button 
            onClick={() => navigate(`/documents/${uploadId}`)}
            className="mt-4 px-4 py-2 bg-white text-red-700 border border-red-200 rounded shadow-sm hover:bg-gray-50"
          >
            Back to Document
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-gray-50 overflow-hidden">
      <header className="bg-white border-b px-6 py-4 flex items-center justify-between shadow-sm z-10">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Artifact Generation Workspace</h1>
          <p className="text-sm text-gray-500 mt-1">Generate presentations from finalized knowledge</p>
        </div>
        <button
          onClick={() => navigate(`/documents/${uploadId}`)}
          className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
        >
          Back to Document
        </button>
      </header>

      <main className="flex-1 overflow-auto p-6 max-w-5xl mx-auto w-full">
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden mb-6">
          <div className="p-6 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900">New Artifact</h2>
            <p className="text-gray-500 text-sm mt-1">
              Using Knowledge Version: <span className="font-mono">{version?.id.slice(0,8)}...</span>
            </p>
          </div>
          <div className="p-6 bg-gray-50">
            <button
              onClick={handleGenerate}
              disabled={!!pollingJob}
              className="w-full flex justify-center py-3 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
            >
              {pollingJob ? "Generating..." : "Generate Presentation (.pptx)"}
            </button>
          </div>
        </div>

        {jobs.length > 0 && (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
            <div className="p-6 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">Generation History</h2>
            </div>
            <ul className="divide-y divide-gray-200">
              {jobs.map(job => (
                <li key={job.id} className="p-6 flex items-center justify-between hover:bg-gray-50 transition-colors">
                  <div>
                    <p className="text-sm font-medium text-gray-900">
                      {job.artifact_type} Presentation
                    </p>
                    <p className="text-sm text-gray-500 flex items-center gap-2 mt-1">
                      <span>{new Date(job.created_at * 1000).toLocaleString()}</span>
                      <span className="text-gray-300">•</span>
                      <span className="font-mono text-xs">{job.id.slice(0,8)}...</span>
                    </p>
                    {job.error_message && (
                      <p className="text-sm text-red-600 mt-2 bg-red-50 p-2 rounded">
                        {job.error_message}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-4">
                    <span className={`px-2.5 py-1 rounded-full text-xs font-medium uppercase tracking-wider
                      ${job.status === ArtifactStatus.COMPLETED ? 'bg-green-100 text-green-800' :
                        job.status === ArtifactStatus.FAILED ? 'bg-red-100 text-red-800' :
                        'bg-blue-100 text-blue-800 animate-pulse'
                      }`}
                    >
                      {job.status}
                    </span>
                    
                    {job.status === ArtifactStatus.COMPLETED && job.artifact_uri && (
                      <a 
                        href={artifactService.getDownloadUrl(job.id)}
                        download
                        className="inline-flex items-center px-3 py-1.5 border border-transparent text-xs font-medium rounded text-indigo-700 bg-indigo-100 hover:bg-indigo-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-colors"
                      >
                        <svg className="mr-1.5 h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                        </svg>
                        Download
                      </a>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </main>
    </div>
  );
}
