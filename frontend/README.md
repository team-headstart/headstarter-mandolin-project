# PA Processor Frontend

A modern, responsive React application for processing Prior Authorization (PA) documents with a beautiful dark/light mode interface.

## Features

- 📁 **File Upload**: Upload referral documents and PA forms
- ⚡ **Real-time Processing**: Process documents with status indicators
- 📥 **File Download**: Download processed forms directly
- 🌙 **Dark/Light Mode**: Toggle between themes
- 🎨 **Animated Background**: Subtle particle animations
- 📱 **Responsive Design**: Works on desktop and mobile
- ♿ **Accessible**: WCAG compliant with proper ARIA labels

## Tech Stack

- **React 18** - Modern React with hooks
- **Tailwind CSS** - Utility-first CSS framework
- **Lucide React** - Beautiful icons
- **HTTP Proxy Middleware** - Development proxy for API calls

## Getting Started

### Prerequisites

- Node.js 16+ 
- npm or yarn
- Backend server running on `http://localhost:8000`

### Installation

1. Install dependencies:
```bash
npm install
```

2. Start the development server:
```bash
npm start
```

3. Open [http://localhost:3000](http://localhost:3000) in your browser

### Development

The app will automatically reload when you make changes to the code.

### Building for Production

```bash
npm run build
```

This creates an optimized production build in the `build` folder.

## API Integration

The frontend connects to the backend API at `/api/v1/process` for document processing. The proxy configuration automatically forwards API requests to the backend during development.

### API Endpoints

- `POST /api/v1/process` - Process PA documents
- `GET /api/v1/download/{filename}` - Download processed files
- `GET /api/v1/files` - List available files

## Project Structure

```
src/
├── components/
│   ├── AnimatedBackground.js  # Floating particles animation
│   ├── FileUpload.js          # File upload component
│   ├── PAProcessor.js         # Main processing interface
│   └── StatusIndicator.js     # Status display component
├── App.js                     # Main app component
├── index.js                   # React entry point
├── index.css                  # Global styles and Tailwind
└── setupProxy.js              # Development proxy configuration
```

## Styling

The application uses Tailwind CSS with custom color schemes for dark and light modes:

### Dark Mode (Default)
- Background: `#000435`
- Text: `#FFFFFF`
- Secondary Text: `#B3B3FF`
- Buttons: `#2D2DFF` / `#1C1CCC`

### Light Mode
- Background: `#F9FAFB`
- Text: `#111827`
- Buttons: `#4F46E5` / `#4338CA`

## Status Indicators

- **Gray** - Waiting for upload
- **Blue** - Processing...
- **Green** - Done
- **Red** - Error

## Contributing

1. Follow the existing code style
2. Ensure all components are accessible
3. Test in both dark and light modes
4. Verify responsive behavior on different screen sizes 