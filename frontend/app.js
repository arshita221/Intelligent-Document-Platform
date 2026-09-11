document.addEventListener('DOMContentLoaded', () => {
    const uploadForm = document.getElementById('upload-form');
    const fileInput = document.getElementById('file-input');
    const fileNameDisplay = document.getElementById('file-name-display');
    const submitBtn = document.getElementById('submit-btn');
    const processingStatus = document.getElementById('processing-status');
    const refreshBtn = document.getElementById('refresh-btn');
    const documentsTableBody = document.getElementById('documents-table-body');

    // Metrics
    const metricTotal = document.getElementById('metric-total');
    const metricPassed = document.getElementById('metric-passed');
    const metricFailed = document.getElementById('metric-failed');

    // Modal & Tabs
    const resultModal = document.getElementById('result-modal');
    const closeModalBtn = document.getElementById('close-modal-btn');
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    const copyJsonBtn = document.getElementById('copy-json-btn');

    let currentDocumentData = null;

    // 1. File Input UI Display
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            const file = e.target.files[0];
            fileNameDisplay.textContent = `Selected: ${file.name} (${(file.size / (1024 * 1024)).toFixed(2)} MB)`;
        } else {
            fileNameDisplay.innerHTML = 'Drag & drop or <span class="browse-link">browse file</span>';
        }
    });

    // 2. Upload Form Handler
    uploadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        if (!fileInput.files || fileInput.files.length === 0) {
            alert('Please select a file to process.');
            return;
        }

        const formData = new FormData(uploadForm);
        
        // Show processing UI
        submitBtn.disabled = true;
        processingStatus.classList.remove('hidden');

        try {
            const response = await fetch('/api/v1/documents/process', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();
            const docData = result.document_name ? result : (result.detail && result.detail.document_name ? result.detail : null);

            if (docData) {
                currentDocumentData = docData;
                openModal(docData);
                loadDocuments();
            } else {
                const detailMsg = result.detail || result;
                alert(`Processing Error: ${typeof detailMsg === 'string' ? detailMsg : JSON.stringify(detailMsg)}`);
            }
        } catch (err) {
            alert(`Network or Server error: ${err.message}`);
        } finally {
            submitBtn.disabled = false;
            processingStatus.classList.add('hidden');
        }
    });

    // 3. Load Documents List & Metrics
    async function loadDocuments() {
        try {
            const res = await fetch('/api/v1/documents');
            if (!res.ok) return;

            const data = await res.json();
            metricTotal.textContent = data.total_count;
            metricPassed.textContent = data.passed_count;
            metricFailed.textContent = data.failed_count;

            if (data.documents.length === 0) {
                documentsTableBody.innerHTML = '<tr><td colspan="6" class="empty-state">No documents processed yet. Upload a file above to begin.</td></tr>';
                return;
            }

            documentsTableBody.innerHTML = data.documents.map(doc => {
                let statusBadgeClass = 'badge-pass';
                if (doc.processing_status === 'FAILED') statusBadgeClass = 'badge-fail';
                if (doc.processing_status === 'INCOMPLETE') statusBadgeClass = 'badge-na';
                const dateStr = new Date(doc.uploaded_at).toLocaleString();

                return `
                    <tr>
                        <td><strong>${escapeHtml(doc.original_filename)}</strong></td>
                        <td>${escapeHtml(doc.document_type.replace('_', ' ').toUpperCase())}</td>
                        <td><span class="badge ${statusBadgeClass}">${doc.processing_status}</span></td>
                        <td>${doc.page_count}</td>
                        <td>${dateStr}</td>
                        <td>
                            <button class="btn btn-secondary btn-sm view-btn" data-doc-name="${doc.document_name}">View</button>
                        </td>
                    </tr>
                `;
            }).join('');

            // Attach view event listeners
            document.querySelectorAll('.view-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const docName = btn.getAttribute('data-doc-name');
                    fetchDocumentDetails(docName);
                });
            });

        } catch (err) {
            console.error('Failed to load documents list:', err);
        }
    }

    refreshBtn.addEventListener('click', loadDocuments);

    // 4. Fetch Single Document Details
    async function fetchDocumentDetails(docName) {
        try {
            const res = await fetch(`/api/v1/documents/${docName}`);
            if (!res.ok) {
                alert('Could not fetch document details.');
                return;
            }
            const data = await res.json();
            currentDocumentData = data;
            openModal(data);
        } catch (err) {
            alert(`Error fetching details: ${err.message}`);
        }
    }

    // 5. Render Result Modal
    function openModal(data) {
        document.getElementById('modal-doc-name').textContent = data.original_filename;
        const statusBadge = document.getElementById('modal-status-badge');
        statusBadge.textContent = data.processing_status;
        let badgeClass = 'badge-pass';
        if (data.processing_status === 'FAILED') badgeClass = 'badge-fail';
        if (data.processing_status === 'INCOMPLETE') badgeClass = 'badge-na';
        statusBadge.className = `badge ${badgeClass}`;


        // Summary Tab
        document.getElementById('detail-filename').textContent = data.original_filename;
        document.getElementById('detail-type').textContent = data.document_type.toUpperCase();
        document.getElementById('detail-mime').textContent = data.file_type;
        document.getElementById('detail-pages').textContent = data.page_count;
        document.getElementById('detail-time').textContent = `${data.processing_metadata.processing_time_seconds}s`;
        document.getElementById('detail-extractor').textContent = data.processing_metadata.extractor_used;

        // File Validation List
        const fv = data.file_validation;
        const fvContainer = document.getElementById('file-validation-details');
        fvContainer.innerHTML = `
            <div class="check-card">
                <div class="check-card-header">
                    <span>File Existence & Non-Emptiness</span>
                    <span class="badge ${fv.file_exists && fv.is_not_empty ? 'badge-pass' : 'badge-fail'}">
                        ${fv.file_exists && fv.is_not_empty ? 'PASS' : 'FAIL'}
                    </span>
                </div>
                <div class="check-card-header">
                    <span>Supported File Signature & Extension</span>
                    <span class="badge ${fv.supported_extension && fv.signature_valid ? 'badge-pass' : 'badge-fail'}">
                        ${fv.supported_extension && fv.signature_valid ? 'PASS' : 'FAIL'}
                    </span>
                </div>
                <div class="check-card-header">
                    <span>PDF Page Count (Max 3 Pages)</span>
                    <span class="badge ${fv.page_count_valid ? 'badge-pass' : 'badge-fail'}">
                        ${fv.page_count_valid ? `PASS (${fv.page_count} Pgs)` : 'FAIL'}
                    </span>
                </div>
                ${fv.errors.length > 0 ? `<div class="operands-list" style="color:var(--status-fail-text);">Errors: ${fv.errors.join('; ')}</div>` : ''}
                ${data.error_message ? `<div class="operands-list" style="color:var(--status-fail-text); margin-top:0.5rem;"><strong>Processing Note:</strong> ${escapeHtml(data.error_message)}</div>` : ''}
            </div>
        `;

        // Deterministic Math Validation Checks Tab
        const valContainer = document.getElementById('validation-checks-container');
        const checks = data.validation.checks || [];

        if (checks.length === 0) {
            valContainer.innerHTML = '<p class="empty-state">No validation checks available.</p>';
        } else {
            valContainer.innerHTML = checks.map(c => {
                let badgeClass = 'badge-pass';
                if (c.status === 'FAIL') badgeClass = 'badge-fail';
                if (c.status === 'NOT_APPLICABLE') badgeClass = 'badge-na';

                const operandsFormatted = Object.entries(c.operands || {})
                    .map(([k, v]) => `<strong>${k}:</strong> ${v !== null ? v : 'null'}`)
                    .join(' | ');

                return `
                    <div class="check-card">
                        <div class="check-card-header">
                            <strong>${escapeHtml(c.check_name)}</strong>
                            <span class="badge ${badgeClass}">${c.status}</span>
                        </div>
                        <div class="check-formula">Formula: ${escapeHtml(c.formula)}</div>
                        <div class="operands-list">Operands: ${operandsFormatted}</div>
                        ${c.calculated_value !== null ? `
                            <div class="operands-list">
                                Calculated: ${c.calculated_value} | Reported: ${c.reported_value} | Variance: ${c.variance} (Tol: ${c.tolerance})
                            </div>
                        ` : ''}
                        ${c.details ? `<div class="operands-list" style="color:var(--text-muted);">${escapeHtml(c.details)}</div>` : ''}
                    </div>
                `;
            }).join('');
        }

        // Extracted Fields / Financial Statement Tab
        const fieldsContainer = document.getElementById('fields-container');
        const fields = data.extracted_data.fields || [];
        const periods = data.extracted_data.periods || [];
        const docType = (data.document_type || data.extracted_data.document_type || '').toLowerCase();

        if (periods.length > 0) {
            let periodHeaders = periods.map(p => `<th>${escapeHtml(p.label)}</th>`).join('');
            let fieldNamesSet = new Set();
            periods.forEach(p => (p.fields || []).forEach(f => fieldNamesSet.add(f.name)));
            let allFieldNames = Array.from(fieldNamesSet);

            let periodTableHtml = `
                <h4 style="margin-bottom:12px;">Multi-Period Financial Statement</h4>
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Financial Row Label</th>
                            ${periodHeaders}
                            <th>Evidence</th>
                            <th>Page</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${allFieldNames.map(fieldName => {
                            let firstFieldWithEvidence = null;
                            let cells = periods.map(p => {
                                let f = (p.fields || []).find(x => x.name.toLowerCase() === fieldName.toLowerCase());
                                if (f && f.evidence && !firstFieldWithEvidence) firstFieldWithEvidence = f;
                                if (!f || (f.value === null && f.normalized_value === null)) {
                                    return '<td style="background-color:rgba(239, 68, 68, 0.08); color:var(--text-muted);"><em style="color:var(--text-muted)">null</em></td>';
                                }
                                let valStr = f.normalized_value !== null ? f.normalized_value : (f.value !== null ? escapeHtml(String(f.value)) : '-');
                                return `<td><strong>${valStr}</strong></td>`;
                            }).join('');

                            let ev = firstFieldWithEvidence ? firstFieldWithEvidence.evidence : '-';
                            let page = firstFieldWithEvidence ? firstFieldWithEvidence.page_number : 1;

                            return `
                                <tr>
                                    <td><strong>${escapeHtml(fieldName)}</strong></td>
                                    ${cells}
                                    <td><small style="color:var(--text-secondary)">${escapeHtml(ev || '-')}</small></td>
                                    <td>${page || 1}</td>
                                </tr>
                            `;
                        }).join('')}
                    </tbody>
                </table>
            `;
            fieldsContainer.innerHTML = periodTableHtml;
        } else if (fields.length === 0) {
            fieldsContainer.innerHTML = '<p class="empty-state">No key-value fields extracted.</p>';
        } else {
            fieldsContainer.innerHTML = `
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Field Name</th>
                            <th>Raw Value</th>
                            <th>Normalized Value</th>
                            <th>Evidence</th>
                            <th>Page</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${fields.map(f => `
                            <tr>
                                <td><strong>${escapeHtml(f.name)}</strong></td>
                                <td>${f.value !== null ? escapeHtml(String(f.value)) : '<em style="color:var(--text-muted)">null</em>'}</td>
                                <td>${f.normalized_value !== null ? f.normalized_value : '<span style="color:var(--text-muted)">null</span>'}</td>
                                <td><small style="color:var(--text-secondary)">${escapeHtml(f.evidence || '-')}</small></td>
                                <td>${f.page_number || 1}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        }

        // Line Items & Tables Tab
        const lineItemsContainer = document.getElementById('lineitems-container');
        const lineItems = data.extracted_data.line_items || [];
        const tables = data.extracted_data.tables || [];

        let lineItemsHtml = '<h4>Line Items</h4>';
        if (lineItems.length === 0) {
            if (docType === 'balance_sheet' || docType === 'profit_loss' || docType === 'cash_flow') {
                lineItemsHtml += '<p class="empty-state">Financial rows for ' + escapeHtml(docType.replace('_', ' ')) + ' are displayed under Extracted Fields / Financial Statement tab.</p>';
            } else {
                lineItemsHtml += '<p class="empty-state">No line items extracted.</p>';
            }
        } else {
            lineItemsHtml += `
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Description</th>
                            <th>Qty</th>
                            <th>Unit Price</th>
                            <th>Taxable Amount</th>
                            <th>Discount</th>
                            <th>Tax</th>
                            <th>Total</th>
                            <th>Evidence</th>
                            <th>Page</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${lineItems.map(li => `
                            <tr>
                                <td>${escapeHtml(li.description || (li.raw_data ? JSON.stringify(li.raw_data) : '-'))}</td>
                                <td>${li.quantity !== null && li.quantity !== undefined ? li.quantity : '-'}</td>
                                <td>${li.unit_price !== null && li.unit_price !== undefined ? li.unit_price : '-'}</td>
                                <td>${li.taxable_amount !== null && li.taxable_amount !== undefined ? li.taxable_amount : (li.amount !== null && li.amount !== undefined ? li.amount : '-')}</td>
                                <td>${li.discount !== null && li.discount !== undefined ? li.discount : '-'}</td>
                                <td>${li.tax !== null && li.tax !== undefined ? li.tax : '-'}</td>
                                <td><strong>${li.total !== null && li.total !== undefined ? li.total : '-'}</strong></td>
                                <td><small style="color:var(--text-secondary)">${escapeHtml(li.evidence || '-')}</small></td>
                                <td>${li.page_number || 1}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        }

        if (tables.length > 0) {
            lineItemsHtml += '<h4 style="margin-top:24px;">Extracted Document Tables</h4>';
            tables.forEach((t, idx) => {
                lineItemsHtml += `<h5 style="margin-top:12px; font-weight:600;">${escapeHtml(t.name || 'Table ' + (idx + 1))} (Page ${t.page_number || 1})</h5>`;
                lineItemsHtml += '<table class="data-table"><thead><tr>';
                (t.headers || []).forEach(h => {
                    lineItemsHtml += `<th>${escapeHtml(h)}</th>`;
                });
                lineItemsHtml += '</tr></thead><tbody>';
                (t.rows || []).forEach(row => {
                    lineItemsHtml += '<tr>';
                    (row || []).forEach(cell => {
                        lineItemsHtml += `<td>${cell !== null && cell !== undefined ? escapeHtml(String(cell)) : '-'}</td>`;
                    });
                    lineItemsHtml += '</tr>';
                });
                lineItemsHtml += '</tbody></table>';
            });
        }

        lineItemsContainer.innerHTML = lineItemsHtml;

        // Raw JSON Tab
        document.getElementById('raw-json-display').textContent = JSON.stringify(data, null, 2);

        resultModal.classList.remove('hidden');
    }

    // Modal Tab Switching
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));

            btn.classList.add('active');
            const targetId = btn.getAttribute('data-tab');
            document.getElementById(targetId).classList.add('active');
        });
    });

    closeModalBtn.addEventListener('click', () => {
        resultModal.classList.add('hidden');
    });

    // Copy JSON to Clipboard
    copyJsonBtn.addEventListener('click', () => {
        if (!currentDocumentData) return;
        navigator.clipboard.writeText(JSON.stringify(currentDocumentData, null, 2))
            .then(() => alert('API Response JSON copied to clipboard!'))
            .catch(err => alert('Failed to copy: ' + err));
    });

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // Initial Load
    loadDocuments();
});
