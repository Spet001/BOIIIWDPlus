const { contextBridge, ipcRenderer } = require('electron');

console.log('Workshop preload loaded');

// Script para ser injetado na página do Steam Workshop
window.addEventListener('DOMContentLoaded', () => {
  console.log('DOM loaded, adding buttons');
  
  // Função para adicionar botões
  const addButtons = () => {
    console.log('Adding buttons to workshop items');
    
    // Selecionar todos os itens do workshop
    const selectors = [
      '.workshopItem',
      '.item',
      '.collectionItem',
      '[data-appid]',
      'a[href*="filedetails"]'
    ];
    
    let items = [];
    
    // Tentar todos os seletores
    selectors.forEach(selector => {
      const found = document.querySelectorAll(selector);
      if (found.length > 0) {
        console.log(`Found ${found.length} items with selector: ${selector}`);
        items = [...items, ...found];
      }
    });
    
    // Se não encontrar com seletores específicos, procurar por links
    if (items.length === 0) {
      const allLinks = document.querySelectorAll('a[href*="filedetails"]');
      console.log(`Found ${allLinks.length} filedetails links`);
      items = [...allLinks];
    }
    
    console.log(`Processing ${items.length} total items`);
    
    items.forEach((item, index) => {
      // Evitar duplicar botões
      if (item.querySelector('.boiiiwd-button-container')) {
        return;
      }
      
      let workshopId = null;
      
      // Extrair ID do workshop
      if (item.href && item.href.includes('filedetails')) {
        const match = item.href.match(/filedetails\/\?id=(\d+)/);
        if (match) workshopId = match[1];
      } else {
        const link = item.querySelector('a[href*="filedetails"]');
        if (link) {
          const match = link.href.match(/filedetails\/\?id=(\d+)/);
          if (match) workshopId = match[1];
        }
      }
      
      if (!workshopId) {
        console.log(`No workshop ID found for item ${index}`);
        return;
      }
      
      console.log(`Adding buttons for workshop ID: ${workshopId}`);
      
      // Criar container para botões
      const buttonContainer = document.createElement('div');
      buttonContainer.className = 'boiiiwd-button-container';
      buttonContainer.style.cssText = `
        position: relative;
        z-index: 9999;
        background: rgba(0, 0, 0, 0.8);
        padding: 5px;
        margin: 2px;
        border-radius: 4px;
        display: flex;
        gap: 5px;
        flex-wrap: wrap;
      `;
      
      // Botão Download
      const downloadBtn = document.createElement('button');
      downloadBtn.textContent = 'Download with BOIIIWD';
      downloadBtn.style.cssText = `
        background: #4CAF50 !important;
        color: white !important;
        border: none !important;
        padding: 6px 12px !important;
        border-radius: 3px !important;
        cursor: pointer !important;
        font-size: 11px !important;
        font-weight: bold !important;
        flex: 1;
        min-width: 120px;
        z-index: 10000;
      `;
      
      // Botão Select
      const selectBtn = document.createElement('button');
      selectBtn.textContent = 'Select Item';
      selectBtn.style.cssText = `
        background: #2196F3 !important;
        color: white !important;
        border: none !important;
        padding: 6px 12px !important;
        border-radius: 3px !important;
        cursor: pointer !important;
        font-size: 11px !important;
        font-weight: bold !important;
        flex: 1;
        min-width: 100px;
        z-index: 10000;
      `;
      
      // Event listeners
      downloadBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        console.log(`Download clicked for ID: ${workshopId}`);
        
        ipcRenderer.send('workshop-download-item', workshopId);
        
        downloadBtn.textContent = 'Downloading...';
        downloadBtn.style.background = '#FF9800 !important';
        
        setTimeout(() => {
          downloadBtn.textContent = 'Download with BOIIIWD';
          downloadBtn.style.background = '#4CAF50 !important';
        }, 2000);
      });
      
      selectBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        console.log(`Select clicked for ID: ${workshopId}`);
        
        ipcRenderer.send('workshop-item-selected', workshopId);
        
        selectBtn.textContent = 'Selected!';
        selectBtn.style.background = '#4CAF50 !important';
        
        setTimeout(() => {
          selectBtn.textContent = 'Select Item';
          selectBtn.style.background = '#2196F3 !important';
        }, 1500);
      });
      
      buttonContainer.appendChild(downloadBtn);
      buttonContainer.appendChild(selectBtn);
      
      // Adicionar ao item
      if (item.tagName === 'A') {
        item.style.position = 'relative';
        item.appendChild(buttonContainer);
      } else {
        item.style.position = 'relative';
        item.appendChild(buttonContainer);
      }
    });
  };
  
  // Executar imediatamente
  addButtons();
  
  // Observar mudanças na página (para conteúdo carregado dinamicamente)
  const observer = new MutationObserver(() => {
    addButtons();
  });
  
  observer.observe(document.body, {
    childList: true,
    subtree: true
  });
  
  // Executar novamente após alguns segundos (para garantir)
  setTimeout(addButtons, 2000);
  setTimeout(addButtons, 5000);
});

console.log('Workshop preload script setup complete');