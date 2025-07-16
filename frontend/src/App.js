import React, { useState, useEffect } from 'react';
import './App.css';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Dashboard Component
const Dashboard = ({ user, stats, matches, applications, onBack }) => {
  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">AutoApplyX Dashboard</h1>
            <p className="text-gray-600 mt-2">Welcome back, {user.name}!</p>
          </div>
          <button
            onClick={onBack}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
          >
            Back to Home
          </button>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          <div className="bg-white p-6 rounded-lg shadow-md">
            <h3 className="text-sm font-medium text-gray-500">Total Applications</h3>
            <p className="text-2xl font-bold text-gray-900">{stats.total_applications}</p>
          </div>
          <div className="bg-white p-6 rounded-lg shadow-md">
            <h3 className="text-sm font-medium text-gray-500">Success Rate</h3>
            <p className="text-2xl font-bold text-green-600">{stats.success_rate}%</p>
          </div>
          <div className="bg-white p-6 rounded-lg shadow-md">
            <h3 className="text-sm font-medium text-gray-500">Skills Detected</h3>
            <p className="text-2xl font-bold text-blue-600">{stats.skills_count}</p>
          </div>
          <div className="bg-white p-6 rounded-lg shadow-md">
            <h3 className="text-sm font-medium text-gray-500">Experience</h3>
            <p className="text-2xl font-bold text-purple-600">{stats.experience_years} years</p>
          </div>
        </div>

        {/* Job Matches */}
        <div className="bg-white rounded-lg shadow-md mb-8">
          <div className="px-6 py-4 border-b border-gray-200">
            <h2 className="text-xl font-semibold text-gray-900">Top Job Matches</h2>
          </div>
          <div className="p-6">
            {matches.length > 0 ? (
              <div className="space-y-4">
                {matches.map((match, index) => (
                  <div key={index} className="border border-gray-200 rounded-lg p-4">
                    <div className="flex justify-between items-start mb-2">
                      <h3 className="font-medium text-gray-900">Job Match {index + 1}</h3>
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                        {(match.similarity_score * 100).toFixed(1)}% Match
                      </span>
                    </div>
                    <p className="text-sm text-gray-600 mb-2">Job ID: {match.job_id}</p>
                    {match.matching_skills.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {match.matching_skills.map((skill, skillIndex) => (
                          <span key={skillIndex} className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                            {skill}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-gray-500 text-center py-8">No matches found. Upload your resume to get started!</p>
            )}
          </div>
        </div>

        {/* User Profile */}
        <div className="bg-white rounded-lg shadow-md">
          <div className="px-6 py-4 border-b border-gray-200">
            <h2 className="text-xl font-semibold text-gray-900">Profile Information</h2>
          </div>
          <div className="p-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Name</label>
                <p className="text-gray-900">{user.name}</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Email</label>
                <p className="text-gray-900">{user.email}</p>
              </div>
              <div className="md:col-span-2">
                <label className="block text-sm font-medium text-gray-700 mb-2">Skills</label>
                <div className="flex flex-wrap gap-2">
                  {user.skills.map((skill, index) => (
                    <span key={index} className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-indigo-100 text-indigo-800">
                      {skill}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// Resume Upload Component
const ResumeUpload = ({ userId, onSuccess }) => {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const handleFileSelect = (selectedFile) => {
    if (selectedFile && (selectedFile.type === 'application/pdf' || selectedFile.type === 'text/plain')) {
      setFile(selectedFile);
    } else {
      alert('Please select a PDF or TXT file');
    }
  };

  const handleUpload = async () => {
    if (!file) return;

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      const response = await axios.post(`${API}/users/${userId}/upload-resume`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      
      alert(`Resume uploaded successfully! Found ${response.data.skills_extracted.length} skills and ${response.data.experience_years} years of experience.`);
      onSuccess(response.data);
    } catch (error) {
      alert('Error uploading resume: ' + (error.response?.data?.detail || error.message));
    } finally {
      setUploading(false);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setDragOver(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const droppedFile = e.dataTransfer.files[0];
    handleFileSelect(droppedFile);
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-xl font-semibold text-gray-900 mb-4">Upload Resume</h2>
      
      <div
        className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
          dragOver
            ? 'border-indigo-500 bg-indigo-50'
            : 'border-gray-300 hover:border-gray-400'
        }`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <svg className="mx-auto h-12 w-12 text-gray-400" stroke="currentColor" fill="none" viewBox="0 0 48 48">
          <path d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        
        <div className="mt-4">
          <p className="text-sm text-gray-600">
            {file ? file.name : 'Drop your resume here or click to browse'}
          </p>
          <p className="text-xs text-gray-500 mt-1">PDF or TXT files only</p>
        </div>
        
        <input
          type="file"
          accept=".pdf,.txt"
          onChange={(e) => handleFileSelect(e.target.files[0])}
          className="hidden"
          id="resume-upload"
        />
        
        <label
          htmlFor="resume-upload"
          className="mt-4 inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-indigo-600 bg-indigo-100 hover:bg-indigo-200 cursor-pointer"
        >
          Select File
        </label>
      </div>
      
      {file && (
        <button
          onClick={handleUpload}
          disabled={uploading}
          className="mt-4 w-full px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {uploading ? 'Uploading...' : 'Upload Resume'}
        </button>
      )}
    </div>
  );
};

// Main App Component
function App() {
  const [currentView, setCurrentView] = useState('home');
  const [users, setUsers] = useState([]);
  const [selectedUser, setSelectedUser] = useState(null);
  const [dashboardData, setDashboardData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [systemStats, setSystemStats] = useState(null);
  const [schedulerStatus, setSchedulerStatus] = useState(null);
  const [realScrapingKeywords, setRealScrapingKeywords] = useState(['software engineer']);
  const [realScrapingLocation, setRealScrapingLocation] = useState('Remote');

  useEffect(() => {
    fetchUsers();
    fetchSystemStats();
    fetchSchedulerStatus();
  }, []);

  const fetchSystemStats = async () => {
    try {
      const response = await axios.get(`${API}/stats/system`);
      setSystemStats(response.data);
    } catch (error) {
      console.error('Error fetching system stats:', error);
    }
  };

  const fetchSchedulerStatus = async () => {
    try {
      const response = await axios.get(`${API}/scheduler/status`);
      setSchedulerStatus(response.data);
    } catch (error) {
      console.error('Error fetching scheduler status:', error);
    }
  };

  const realJobScraping = async (userId = null) => {
    try {
      const keywords = realScrapingKeywords.join(',');
      const params = userId ? 
        `?user_id=${userId}&keywords=${keywords}&location=${realScrapingLocation}` :
        `?keywords=${keywords}&location=${realScrapingLocation}`;
      
      const response = await axios.post(`${API}/scrape/real${params}`);
      alert(`Real job scraping completed! Found ${response.data.jobs_created} jobs for "${keywords}" in ${realScrapingLocation}`);
      
      // Refresh jobs and stats
      const jobsResponse = await axios.get(`${API}/jobs`);
      setJobs(jobsResponse.data);
      await fetchSystemStats();
    } catch (error) {
      alert('Error with real job scraping: ' + (error.response?.data?.detail || error.message));
    }
  };

  const testApplication = async (userId, jobId) => {
    try {
      const response = await axios.post(`${API}/apply/test?user_id=${userId}&job_id=${jobId}`);
      alert(`Application test completed! Status: ${response.data.application_result.status}`);
      
      // Refresh data
      await fetchSystemStats();
    } catch (error) {
      alert('Error testing application: ' + (error.response?.data?.detail || error.message));
    }
  };

  const startScheduler = async () => {
    try {
      const response = await axios.post(`${API}/scheduler/start`);
      alert('Scheduler started successfully! The system will now run autonomously.');
      await fetchSchedulerStatus();
    } catch (error) {
      alert('Error starting scheduler: ' + (error.response?.data?.detail || error.message));
    }
  };

  const fetchUsers = async () => {
    try {
      const response = await axios.get(`${API}/users`);
      setUsers(response.data);
    } catch (error) {
      console.error('Error fetching users:', error);
    }
  };

  const createUser = async (name, email) => {
    try {
      const response = await axios.post(`${API}/users`, { name, email });
      setUsers([...users, response.data]);
      return response.data;
    } catch (error) {
      alert('Error creating user: ' + (error.response?.data?.detail || error.message));
    }
  };

  const loadDashboard = async (userId) => {
    setLoading(true);
    try {
      const response = await axios.get(`${API}/dashboard/${userId}`);
      setDashboardData(response.data);
      setSelectedUser(response.data.user);
      setCurrentView('dashboard');
    } catch (error) {
      alert('Error loading dashboard: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  const testScraping = async () => {
    try {
      const response = await axios.post(`${API}/scrape/test`);
      alert(`Test scraping completed! Created ${response.data.jobs_created} sample jobs.`);
      
      // Fetch updated jobs
      const jobsResponse = await axios.get(`${API}/jobs`);
      setJobs(jobsResponse.data);
    } catch (error) {
      alert('Error testing scraping: ' + (error.response?.data?.detail || error.message));
    }
  };

  const HomeView = () => {
    const [showUserForm, setShowUserForm] = useState(false);
    const [newUserName, setNewUserName] = useState('');
    const [newUserEmail, setNewUserEmail] = useState('');

    const handleCreateUser = async (e) => {
      e.preventDefault();
      if (newUserName && newUserEmail) {
        await createUser(newUserName, newUserEmail);
        setNewUserName('');
        setNewUserEmail('');
        setShowUserForm(false);
      }
    };

    return (
      <div className="min-h-screen bg-gradient-to-br from-indigo-100 to-purple-100">
        <div className="max-w-6xl mx-auto px-4 py-12">
          {/* Header */}
          <div className="text-center mb-12">
            <h1 className="text-5xl font-bold text-gray-900 mb-4">
              Auto<span className="text-indigo-600">Apply</span>X
            </h1>
            <p className="text-xl text-gray-600 max-w-2xl mx-auto">
              The fully autonomous job application system that finds, matches, and applies to jobs 24/7 without human intervention.
            </p>
          </div>

          {/* Features */}
          <div className="grid md:grid-cols-3 gap-8 mb-12">
            <div className="bg-white p-6 rounded-lg shadow-md">
              <div className="w-12 h-12 bg-indigo-100 rounded-lg flex items-center justify-center mb-4">
                <svg className="w-6 h-6 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">AI Resume Analysis</h3>
              <p className="text-gray-600">Advanced parsing extracts skills, experience, and preferences from your resume.</p>
            </div>
            
            <div className="bg-white p-6 rounded-lg shadow-md">
              <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center mb-4">
                <svg className="w-6 h-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">Smart Job Matching</h3>
              <p className="text-gray-600">Vector similarity search finds the most relevant job opportunities for you.</p>
            </div>
            
            <div className="bg-white p-6 rounded-lg shadow-md">
              <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center mb-4">
                <svg className="w-6 h-6 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">Automated Applications</h3>
              <p className="text-gray-600">Runs 24/7 to automatically apply to matching jobs with your personalized profile.</p>
            </div>
          </div>

          {/* User Management */}
          <div className="bg-white rounded-lg shadow-md p-6 mb-8">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-semibold text-gray-900">User Profiles</h2>
              <button
                onClick={() => setShowUserForm(!showUserForm)}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
              >
                Add User
              </button>
            </div>

            {showUserForm && (
              <form onSubmit={handleCreateUser} className="mb-4 p-4 bg-gray-50 rounded-lg">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <input
                    type="text"
                    placeholder="Name"
                    value={newUserName}
                    onChange={(e) => setNewUserName(e.target.value)}
                    className="px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    required
                  />
                  <input
                    type="email"
                    placeholder="Email"
                    value={newUserEmail}
                    onChange={(e) => setNewUserEmail(e.target.value)}
                    className="px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    required
                  />
                </div>
                <button
                  type="submit"
                  className="mt-4 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
                >
                  Create User
                </button>
              </form>
            )}

            <div className="space-y-2">
              {users.map((user) => (
                <div key={user.id} className="flex justify-between items-center p-3 bg-gray-50 rounded-lg">
                  <div>
                    <p className="font-medium text-gray-900">{user.name}</p>
                    <p className="text-sm text-gray-600">{user.email}</p>
                  </div>
                  <button
                    onClick={() => loadDashboard(user.id)}
                    disabled={loading}
                    className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
                  >
                    {loading ? 'Loading...' : 'View Dashboard'}
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Test Controls */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">Test Features</h2>
            <div className="space-y-4">
              <button
                onClick={testScraping}
                className="w-full px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
              >
                Test Job Scraping (Create Sample Jobs)
              </button>
              
              {jobs.length > 0 && (
                <div className="mt-4">
                  <h3 className="font-medium text-gray-900 mb-2">Sample Jobs Created:</h3>
                  <div className="space-y-2">
                    {jobs.slice(0, 3).map((job) => (
                      <div key={job.id} className="p-3 bg-gray-50 rounded-lg">
                        <p className="font-medium">{job.title} at {job.company}</p>
                        <p className="text-sm text-gray-600">{job.location} • {job.source}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  };

  if (currentView === 'dashboard' && dashboardData) {
    return (
      <Dashboard
        user={dashboardData.user}
        stats={dashboardData.stats}
        matches={dashboardData.matches}
        applications={dashboardData.applications}
        onBack={() => setCurrentView('home')}
      />
    );
  }

  if (currentView === 'upload' && selectedUser) {
    return (
      <div className="min-h-screen bg-gray-50">
        <div className="max-w-2xl mx-auto px-4 py-8">
          <button
            onClick={() => setCurrentView('home')}
            className="mb-6 text-indigo-600 hover:text-indigo-800"
          >
            ← Back to Home
          </button>
          
          <ResumeUpload
            userId={selectedUser.id}
            onSuccess={() => {
              setCurrentView('home');
              fetchUsers();
            }}
          />
        </div>
      </div>
    );
  }

  return <HomeView />;
}

export default App;