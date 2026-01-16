import React, { useState } from 'react';
import { Upload, Download, Play, AlertCircle, CheckCircle, Clock, FileText } from 'lucide-react';
import FileUpload from './FileUpload';
import StatusIndicator from './StatusIndicator';

const PAProcessor = ({ isDarkMode }) => {
  const [document1, setDocument1] = useState(null);
  const [document2, setDocument2] = useState(null);
  const [status, setStatus] = useState('waiting'); // waiting, processing, done, error
  const [resultUrl, setResultUrl] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');

  const handleProcess = async () => {
    if (!document1 || !document2) {
      setErrorMessage('Please upload both documents before processing.');
      return;
    }

    setStatus('processing');
    setErrorMessage('');

    const formData = new FormData();
    formData.append('referral_document', document1);
    formData.append('pa_form', document2);

    try {
      const response = await fetch('/api/v1/process', {
        method: 'POST',
        body: formData,
      });

      if (response.ok) {
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        setResultUrl(url);
        setStatus('done');
      } else {
        let errorMessage = 'Processing failed. Please try again.';
        try {
          const errorData = await response.json();
          errorMessage = errorData.detail || errorMessage;
        } catch (e) {
          // If response is not JSON, use default message
        }
        setErrorMessage(errorMessage);
        setStatus('error');
      }
    } catch (error) {
      setErrorMessage('Network error. Please check your connection and try again.');
      setStatus('error');
    }
  };

  const handleDownload = () => {
    if (resultUrl) {
      const link = document.createElement('a');
      link.href = resultUrl;
      link.download = 'processed_pa_form.pdf';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
  };

  const resetForm = () => {
    setDocument1(null);
    setDocument2(null);
    setStatus('waiting');
    setResultUrl(null);
    setErrorMessage('');
  };

  return (
    <div className={`rounded-2xl p-8 ${
      isDarkMode ? 'glass-effect' : 'glass-effect-light'
    }`}>
      {/* Header */}
      <div className="text-center mb-8">
        <h2 className={`text-3xl font-bold mb-2 ${
          isDarkMode ? 'text-dark-text' : 'text-light-text'
        }`}>
          Process PA Documents
        </h2>
        <p className={`text-lg ${
          isDarkMode ? 'text-dark-text-secondary' : 'text-gray-600'
        }`}>
          Upload your referral document and PA form to automatically process and fill the form
        </p>
      </div>

      {/* File Upload Section */}
      <div className="grid md:grid-cols-2 gap-6 mb-8">
        <FileUpload
          label="Document 1 (Referral)"
          file={document1}
          onFileChange={setDocument1}
          isDarkMode={isDarkMode}
          accept=".pdf"
        />
        <FileUpload
          label="Document 2 (PA Form)"
          file={document2}
          onFileChange={setDocument2}
          isDarkMode={isDarkMode}
          accept=".pdf"
        />
      </div>

      {/* Status Section */}
      <div className="mb-8">
        <StatusIndicator status={status} isDarkMode={isDarkMode} />
        {errorMessage && (
          <div className="mt-4 p-4 rounded-lg bg-status-red/10 border border-status-red/20">
            <div className="flex items-center space-x-2">
              <AlertCircle className="w-5 h-5 text-status-red" />
              <span className={`text-status-red ${
                isDarkMode ? 'text-dark-text' : 'text-light-text'
              }`}>
                {errorMessage}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Action Buttons */}
      <div className="flex flex-col sm:flex-row gap-4 justify-center">
        {status === 'waiting' && (
          <button
            onClick={handleProcess}
            disabled={!document1 || !document2}
            className={`flex items-center justify-center space-x-2 px-8 py-3 rounded-lg font-semibold transition-all duration-200 ${
              document1 && document2
                ? isDarkMode
                  ? 'bg-dark-button hover:bg-dark-button-hover text-white'
                  : 'bg-light-button hover:bg-light-button-hover text-white'
                : 'bg-gray-400 cursor-not-allowed text-gray-200'
            }`}
          >
            <Play className="w-5 h-5" />
            <span>Process Documents</span>
          </button>
        )}

        {status === 'done' && (
          <>
            <button
              onClick={handleDownload}
              className={`flex items-center justify-center space-x-2 px-8 py-3 rounded-lg font-semibold transition-all duration-200 ${
                isDarkMode
                  ? 'bg-status-green hover:bg-green-600 text-white'
                  : 'bg-status-green hover:bg-green-600 text-white'
              }`}
            >
              <Download className="w-5 h-5" />
              <span>Download Result</span>
            </button>
            <button
              onClick={resetForm}
              className={`flex items-center justify-center space-x-2 px-8 py-3 rounded-lg font-semibold transition-all duration-200 ${
                isDarkMode
                  ? 'bg-dark-button hover:bg-dark-button-hover text-white'
                  : 'bg-light-button hover:bg-light-button-hover text-white'
              }`}
            >
              <FileText className="w-5 h-5" />
              <span>Process New Documents</span>
            </button>
          </>
        )}

        {status === 'error' && (
          <button
            onClick={resetForm}
            className={`flex items-center justify-center space-x-2 px-8 py-3 rounded-lg font-semibold transition-all duration-200 ${
              isDarkMode
                ? 'bg-dark-button hover:bg-dark-button-hover text-white'
                : 'bg-light-button hover:bg-light-button-hover text-white'
            }`}
          >
            <FileText className="w-5 h-5" />
            <span>Try Again</span>
          </button>
        )}
      </div>

      {/* Instructions */}
      <div className={`mt-8 p-6 rounded-lg ${
        isDarkMode ? 'bg-white/5' : 'bg-black/5'
      }`}>
        <h3 className={`text-lg font-semibold mb-3 ${
          isDarkMode ? 'text-dark-text' : 'text-light-text'
        }`}>
          Instructions
        </h3>
        <ul className={`space-y-2 text-sm ${
          isDarkMode ? 'text-dark-text-secondary' : 'text-gray-600'
        }`}>
          <li>• Document 1 should be the referral document containing patient information</li>
          <li>• Document 2 should be the PA form that needs to be filled</li>
          <li>• Both documents must be in PDF format</li>
          <li>• The system will automatically extract data and fill the form</li>
          <li>• Download the processed form when complete</li>
        </ul>
      </div>
    </div>
  );
};

export default PAProcessor; 