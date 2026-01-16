import React from 'react';
import { Clock, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';

const statusMap = {
  waiting: {
    color: 'status-gray',
    text: 'Waiting for upload',
    icon: <Clock className="w-5 h-5" />,
  },
  processing: {
    color: 'status-blue',
    text: 'Processing...',
    icon: <Loader2 className="w-5 h-5 animate-spin" />,
  },
  done: {
    color: 'status-green',
    text: 'Done',
    icon: <CheckCircle className="w-5 h-5" />,
  },
  error: {
    color: 'status-red',
    text: 'Error',
    icon: <AlertCircle className="w-5 h-5" />,
  },
};

const StatusIndicator = ({ status, isDarkMode }) => {
  const { color, text, icon } = statusMap[status] || statusMap['waiting'];
  return (
    <div className={`flex items-center justify-center space-x-2 text-lg font-semibold transition-colors duration-200`}> 
      <span className={`text-${color}`}>{icon}</span>
      <span className={`text-${color} ${isDarkMode ? 'text-dark-text' : 'text-light-text'}`}>{text}</span>
    </div>
  );
};

export default StatusIndicator; 