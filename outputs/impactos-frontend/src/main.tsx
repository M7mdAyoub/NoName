import React from 'react';
import ReactDOM from 'react-dom/client';
import {WorkspaceProvider} from './workspace/Context';
import Workspace from './workspace/Workspace';
import '@fontsource/ibm-plex-sans-arabic/400.css';
import '@fontsource/ibm-plex-sans-arabic/500.css';
import '@fontsource/ibm-plex-sans-arabic/600.css';
import './workspace/workspace.css';
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><WorkspaceProvider><Workspace/></WorkspaceProvider></React.StrictMode>);
