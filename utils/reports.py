"""Report generation utilities (Excel and log files)."""

import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

from utils.config import (
    REPORT_FILENAME_TEMPLATE,
    LOG_FILENAME_TEMPLATE,
    TIMESTAMP_FORMAT,
    EXCEL_SHEET_NAME,
    EXCEL_HEADERS,
    MAX_COLUMN_WIDTH
)


class ReportGenerator:
    """Generates Excel and log reports."""
    
    def __init__(self, output_dir: Path, logger: logging.Logger):
        """
        Initialize report generator.
        
        Args:
            output_dir: Directory where reports will be saved
            logger: Logger instance
        """
        self.output_dir = output_dir
        self.logger = logger
    
    def create_excel_report(
        self,
        downloaded_files: List[Dict],
        duplicate_files: Optional[List[Dict]] = None,
        latest_irt_record: Optional[Dict] = None,
        latest_irt_date_range: Optional[str] = None,
    ) -> Optional[Path]:
        """
        Create Excel report of downloaded documents and duplicates.
        
        Args:
            downloaded_files: List of dictionaries with 'Document Number' and 'Filename'
            duplicate_files: Optional list of duplicate records with columns:
                            LNI, File Name, Decided Date, Received Date, Route, Source Detail
            latest_irt_record: Optional most recent IRT record for zero-download runs
            latest_irt_date_range: Optional IRT lookup window used for latest_irt_record
            
        Returns:
            Path to created Excel file or None if failed
        """
        timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
        report_filename = REPORT_FILENAME_TEMPLATE.format(timestamp=timestamp)
        report_path = self.output_dir / report_filename
        self.logger.info(f"Creating Excel report at: {report_path}")
        
        try:
            wb = openpyxl.Workbook()
            
            # Remove default sheet if no downloaded files
            if downloaded_files:
                ws = wb.active
                ws.title = EXCEL_SHEET_NAME
                
                # Headers
                ws.append(EXCEL_HEADERS)
                
                # Style headers
                for cell in ws[1]:
                    cell.font = Font(bold=True)
                    cell.alignment = Alignment(horizontal='center')
                
                # Add data
                for file_info in downloaded_files:
                    ws.append([
                        file_info.get('Document Number', ''),
                        file_info.get('Filename', '')
                    ])
                
                # Auto-adjust column widths
                self._adjust_column_widths(ws)
            else:
                # Remove default sheet if no downloaded files
                wb.remove(wb.active)
            
            # Create duplicate sheet if duplicates exist
            if duplicate_files:
                ws_duplicates = wb.create_sheet("Documents Already Online")
                
                # Headers for duplicates
                duplicate_headers = ['LNI', 'File Name', 'Decided Date', 
                                    'Received Date', 'Route', 'Source Detail']
                ws_duplicates.append(duplicate_headers)
                
                # Style headers
                for cell in ws_duplicates[1]:
                    cell.font = Font(bold=True)
                    cell.alignment = Alignment(horizontal='center')
                
                # Add duplicate data
                for record in duplicate_files:
                    ws_duplicates.append([
                        record.get('LNI', ''),
                        record.get('File Name', ''),
                        record.get('Decided Date', ''),
                        record.get('Received Date', ''),
                        record.get('Route', ''),
                        record.get('Source Detail', '')
                    ])
                
                # Auto-adjust column widths
                self._adjust_column_widths(ws_duplicates)
            
            # Ensure at least one sheet exists (openpyxl requirement)
            if len(wb.worksheets) == 0:
                ws = wb.create_sheet("Summary")
                start_date_value = "N/A"
                end_date_value = "N/A"

                if latest_irt_date_range:
                    if " to " in latest_irt_date_range:
                        start_date_value, end_date_value = [
                            part.strip() for part in latest_irt_date_range.split(" to ", 1)
                        ]
                    else:
                        start_date_value = latest_irt_date_range.strip()

                summary_headers = [
                    "Start Date",
                    "End Date",
                    "Most Recent File Name",
                    "Most Recent LNI",
                    "Most Recent Received Date",
                ]
                ws.append(summary_headers)

                ws.append([
                    start_date_value,
                    end_date_value,
                    latest_irt_record.get('File Name', 'N/A') if latest_irt_record else "N/A",
                    latest_irt_record.get('LNI', 'N/A') if latest_irt_record else "N/A",
                    latest_irt_record.get('Received Date', 'N/A') if latest_irt_record else "N/A",
                ])

                self._apply_summary_table_style(ws)
                self._adjust_column_widths(ws)
            
            wb.save(report_path)
            self.logger.info(f"Excel report created: {report_filename}")
            return report_path
            
        except Exception as e:
            self.logger.error(f"Error creating Excel report: {e}")
            return None
    
    def _adjust_column_widths(self, worksheet):
        """Adjust column widths to fit content."""
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            
            for cell in column:
                try:
                    if cell.value and len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            
            adjusted_width = min(max_length + 2, MAX_COLUMN_WIDTH)
            worksheet.column_dimensions[column_letter].width = adjusted_width

    def _apply_summary_table_style(self, worksheet):
        """Apply centered alignment, white header fill, and all borders."""
        thin_side = Side(style='thin', color='000000')
        all_borders = Border(
            left=thin_side,
            right=thin_side,
            top=thin_side,
            bottom=thin_side,
        )
        header_fill = PatternFill(
            fill_type='solid',
            fgColor='FF50DCB7',
            start_color='FF50DCB7',
            end_color='FF50DCB7',
        )

        for row in worksheet.iter_rows():
            for cell in row:
                cell.alignment = Alignment(horizontal='center', vertical='center')
                cell.border = all_borders

                if cell.row == 1:
                    cell.font = Font(bold=True)
                    cell.fill = header_fill

    def create_log_report(
        self,
        date_str: str,
        downloaded_files: List[Dict],
        duplicate_files: Optional[List[Dict]] = None,
        log_file_path: Optional[Path] = None,
        latest_irt_record: Optional[Dict] = None,
        latest_irt_date_range: Optional[str] = None,
    ) -> Optional[Path]:
        """
        Prepend summary section to existing log file (which contains all execution logs).
        
        Args:
            date_str: Date string used for collection
            downloaded_files: List of downloaded file information
            duplicate_files: Optional list of duplicate records
            log_file_path: Path to existing log file to prepend summary to
            latest_irt_record: Optional most recent IRT record for zero-download runs
            latest_irt_date_range: Optional IRT lookup window used for latest_irt_record
            
        Returns:
            Path to log file or None if failed
        """
        if not log_file_path:
            # Fallback: create new file if path not provided
            timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
            log_filename = LOG_FILENAME_TEMPLATE.format(timestamp=timestamp)
            log_file_path = self.output_dir / log_filename
        
        self.logger.info(f"Prepending summary to log file: {log_file_path}")
        
        try:
            # Read existing execution logs
            execution_logs = ""
            if log_file_path.exists():
                with open(log_file_path, 'r', encoding='utf-8') as f:
                    execution_logs = f.read()
            
            # Write summary first, then execution logs
            with open(log_file_path, 'w', encoding='utf-8') as f:
                # Write summary section at the top
                f.write("=" * 70 + "\n")
                f.write("SUMMARY REPORT\n")
                f.write("=" * 70 + "\n\n")
                f.write(f"Collection Date: {date_str}\n")
                f.write(f"Files Downloaded: {len(downloaded_files)}\n")
                f.write(f"Duplicates Found: {len(duplicate_files) if duplicate_files else 0}\n\n")

                if latest_irt_record or latest_irt_date_range:
                    f.write("-" * 70 + "\n")
                    f.write("MOST RECENT FCC DOCUMENT\n")
                    f.write("-" * 70 + "\n\n")
                    if latest_irt_date_range:
                        f.write(f"Date Range: {latest_irt_date_range}\n")
                    if latest_irt_record:
                        f.write(
                            f"File Name: {latest_irt_record.get('File Name', 'N/A')}\n"
                        )
                        f.write(f"LNI: {latest_irt_record.get('LNI', 'N/A')}\n")
                        f.write(
                            f"Received Date: {latest_irt_record.get('Received Date', 'N/A')}\n\n"
                        )
                    else:
                        f.write("No recent FCC document could be determined.\n\n")
                
                if downloaded_files:
                    f.write("-" * 70 + "\n")
                    f.write("DOWNLOADED FILES\n")
                    f.write("-" * 70 + "\n\n")
                    for file_info in downloaded_files:
                        f.write(f"Document Number: {file_info.get('Document Number', 'N/A')}\n")
                        f.write(f"Filename: {file_info.get('Filename', 'N/A')}\n\n")
                
                if duplicate_files:
                    f.write("\n" + "-" * 70 + "\n")
                    f.write("DOCUMENTS ALREADY ONLINE\n")
                    f.write("-" * 70 + "\n\n")
                    for record in duplicate_files:
                        f.write(f"LNI: {record.get('LNI', 'N/A')}\n")
                        f.write(f"File Name: {record.get('File Name', 'N/A')}\n")
                        f.write(f"Decided Date: {record.get('Decided Date', 'N/A')}\n")
                        f.write(f"Received Date: {record.get('Received Date', 'N/A')}\n")
                        f.write(f"Route: {record.get('Route', 'N/A')}\n")
                        f.write(f"Source Detail: {record.get('Source Detail', 'N/A')}\n\n")
                
                # Write separator
                f.write("\n" + "=" * 70 + "\n")
                f.write("EXECUTION LOG\n")
                f.write("=" * 70 + "\n\n")
                
                # Write all execution logs after the summary
                f.write(execution_logs)
            
            self.logger.info(f"Summary prepended to log file")
            return log_file_path
            
        except Exception as e:
            self.logger.error(f"Error prepending summary to log file: {e}")
            return None

