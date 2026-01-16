import React from 'react';
import { Upload, X } from 'lucide-react';

const FileUpload = ({ label, file, onFileChange, isDarkMode, accept }) => {
  const handleChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      onFileChange(e.target.files[0]);
    }
  };

  const handleRemove = () => {
    onFileChange(null);
  };

  return (
    <div className={`flex flex-col items-center p-6 rounded-xl border-2 border-dashed transition-colors duration-200 ${
      isDarkMode
        ? 'border-dark-text-secondary bg-white/5'
        : 'border-light-button bg-black/5'
    }`}>
      <label className="w-full text-center cursor-pointer" htmlFor={label}>
        <span className={`block mb-2 font-semibold ${isDarkMode ? 'text-dark-text' : 'text-light-text'}`}>{label}</span>
        <input
          id={label}
          type="file"
          accept={accept}
          className="hidden"
          onChange={handleChange}
          aria-label={label}
        />
        {!file ? (
          <div className="flex flex-col items-center justify-center">
            <Upload className={`w-8 h-8 mb-2 ${isDarkMode ? 'text-dark-text-secondary' : 'text-light-button'}`} />
            <span className={`text-sm ${isDarkMode ? 'text-dark-text-secondary' : 'text-gray-600'}`}>Click to upload</span>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center">
            <span className={`truncate max-w-xs text-sm mb-2 ${isDarkMode ? 'text-dark-text' : 'text-light-text'}`}>{file.name}</span>
            <button
              type="button"
              onClick={handleRemove}
              className={`flex items-center px-3 py-1 rounded bg-status-red/20 hover:bg-status-red/40 text-status-red text-xs font-semibold transition-all duration-200`}
              aria-label="Remove file"
            >
              <X className="w-4 h-4 mr-1" /> Remove
            </button>
          </div>
        )}
      </label>
    </div>
  );
};

export default FileUpload; 