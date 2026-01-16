import React, { useState, useEffect } from 'react';
import { Moon, Sun, Upload } from 'lucide-react';
import PAProcessor from './components/PAProcessor';

function App() {
  const [isDarkMode, setIsDarkMode] = useState(true);

  useEffect(() => {
    // Apply dark mode class to body
    if (isDarkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDarkMode]);

  return (
    <div className={`min-h-screen ${isDarkMode ? 'gradient-bg-dark' : 'gradient-bg-light'}`}>
      {/* Header */}
      <header className="relative z-10 p-6">
        <div className="max-w-7xl mx-auto flex justify-between items-center">
          <div className="flex items-center space-x-3">
            <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
              isDarkMode 
                ? 'bg-dark-button text-dark-text' 
                : 'bg-light-button text-white'
            }`}>
              <Upload className="w-6 h-6" />
            </div>
            <h1 className={`text-2xl font-bold ${
              isDarkMode ? 'text-dark-text' : 'text-light-text'
            }`}>
              PA Processor and Form Filler
            </h1>
          </div>
          
          {/* Theme Toggle */}
          <button
            onClick={() => setIsDarkMode(!isDarkMode)}
            className={`p-3 rounded-lg transition-all duration-200 ${
              isDarkMode 
                ? 'glass-effect hover:bg-white/20' 
                : 'glass-effect-light hover:bg-black/5'
            }`}
            aria-label="Toggle dark mode"
          >
            {isDarkMode ? (
              <Sun className={`w-5 h-5 ${isDarkMode ? 'text-dark-text' : 'text-light-text'}`} />
            ) : (
              <Moon className={`w-5 h-5 ${isDarkMode ? 'text-dark-text' : 'text-light-text'}`} />
            )}
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className="relative z-10 px-6 pb-6">
        <div className="max-w-4xl mx-auto">
          <PAProcessor isDarkMode={isDarkMode} />
        </div>
      </main>
    </div>
  );
}

export default App; 