      *================================================================*
      * PROGRAM:     LOAN-PROCESS                                      *
      * SYSTEM:      Retail Banking Loan Origination & Servicing       *
      * DESCRIPTION: Full loan lifecycle — application intake,         *
      *              credit scoring, amortisation schedule generation,  *
      *              payment processing, delinquency management,        *
      *              regulatory reporting (Basel III RWA calc),         *
      *              and GL posting.                                    *
      * AUTHOR:      Core Banking Platform Team                        *
      * DATE:        2026-05-28                                         *
      * VERSION:     4.7.2                                              *
      *================================================================*
       IDENTIFICATION DIVISION.
       PROGRAM-ID. LOAN-PROCESS.
       AUTHOR. CORE-BANKING-TEAM.
       DATE-WRITTEN. 2026-05-28.
       DATE-COMPILED. 2026-05-28.
       SECURITY. CONFIDENTIAL-INTERNAL.

       ENVIRONMENT DIVISION.
       CONFIGURATION SECTION.
       SOURCE-COMPUTER. IBM-Z16.
       OBJECT-COMPUTER. IBM-Z16
           SEQUENCE IS EBCDIC.
       SPECIAL-NAMES.
           DECIMAL-POINT IS COMMA.

       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT LOAN-MASTER-FILE
               ASSIGN TO UT-S-LOANMAST
               ORGANIZATION IS INDEXED
               ACCESS MODE IS DYNAMIC
               RECORD KEY IS LM-LOAN-ID
               ALTERNATE RECORD KEY IS LM-CUSTOMER-ID
                   WITH DUPLICATES
               FILE STATUS IS WS-FILE-STATUS-1.

           SELECT PAYMENT-HISTORY-FILE
               ASSIGN TO UT-S-PAYHIST
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE IS SEQUENTIAL
               FILE STATUS IS WS-FILE-STATUS-2.

           SELECT GL-POSTING-FILE
               ASSIGN TO UT-S-GLPOST
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE IS SEQUENTIAL
               FILE STATUS IS WS-FILE-STATUS-3.

           SELECT REPORT-OUTPUT-FILE
               ASSIGN TO UT-S-RPTOUT
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-FILE-STATUS-4.

           SELECT ERROR-LOG-FILE
               ASSIGN TO UT-S-ERRLOG
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-FILE-STATUS-5.

       DATA DIVISION.
       FILE SECTION.

       FD  LOAN-MASTER-FILE
           LABEL RECORDS ARE STANDARD
           RECORD CONTAINS 512 CHARACTERS
           BLOCK CONTAINS 100 RECORDS.
       01  LOAN-MASTER-RECORD.
           05  LM-LOAN-ID              PIC X(15).
           05  LM-CUSTOMER-ID          PIC X(12).
           05  LM-LOAN-TYPE            PIC X(3).
           05  LM-PRINCIPAL            PIC 9(13)V99  COMP-3.
           05  LM-OUTSTANDING-BAL      PIC 9(13)V99  COMP-3.
           05  LM-INTEREST-RATE        PIC 9(2)V9(6) COMP-3.
           05  LM-ORIGINATION-DATE     PIC 9(8).
           05  LM-MATURITY-DATE        PIC 9(8).
           05  LM-NEXT-PAYMENT-DATE    PIC 9(8).
           05  LM-MONTHLY-PAYMENT      PIC 9(11)V99  COMP-3.
           05  LM-TOTAL-PAID           PIC 9(13)V99  COMP-3.
           05  LM-DAYS-PAST-DUE        PIC 9(4)      COMP.
           05  LM-CREDIT-SCORE         PIC 9(3).
           05  LM-LTV-RATIO            PIC 9(3)V99   COMP-3.
           05  LM-DTI-RATIO            PIC 9(3)V99   COMP-3.
           05  LM-COLLATERAL-VALUE     PIC 9(13)V99  COMP-3.
           05  LM-STATUS               PIC X(2).
           05  LM-RISK-GRADE           PIC X(2).
           05  LM-PROVISION-PCT        PIC 9(1)V9(4) COMP-3.
           05  LM-RWA-WEIGHT           PIC 9(3)V99   COMP-3.
           05  LM-BRANCH-CODE          PIC X(6).
           05  LM-OFFICER-ID           PIC X(8).
           05  LM-LAST-REVIEW-DATE     PIC 9(8).
           05  LM-FILLER               PIC X(270).

       FD  PAYMENT-HISTORY-FILE
           LABEL RECORDS ARE STANDARD
           RECORD CONTAINS 128 CHARACTERS.
       01  PAYMENT-HISTORY-RECORD.
           05  PH-LOAN-ID              PIC X(15).
           05  PH-PAYMENT-DATE         PIC 9(8).
           05  PH-AMOUNT-DUE           PIC 9(11)V99  COMP-3.
           05  PH-AMOUNT-PAID          PIC 9(11)V99  COMP-3.
           05  PH-PRINCIPAL-PORTION    PIC 9(11)V99  COMP-3.
           05  PH-INTEREST-PORTION     PIC 9(11)V99  COMP-3.
           05  PH-LATE-FEE             PIC 9(7)V99   COMP-3.
           05  PH-PAYMENT-METHOD       PIC X(3).
           05  PH-STATUS               PIC X(1).
           05  PH-FILLER               PIC X(38).

       FD  GL-POSTING-FILE
           LABEL RECORDS ARE STANDARD
           RECORD CONTAINS 256 CHARACTERS.
       01  GL-POSTING-RECORD.
           05  GL-JOURNAL-ID           PIC X(20).
           05  GL-ACCOUNT-CODE         PIC X(12).
           05  GL-COST-CENTRE          PIC X(8).
           05  GL-DEBIT-AMOUNT         PIC 9(13)V99  COMP-3.
           05  GL-CREDIT-AMOUNT        PIC 9(13)V99  COMP-3.
           05  GL-DESCRIPTION          PIC X(60).
           05  GL-POSTING-DATE         PIC 9(8).
           05  GL-CURRENCY             PIC X(3).
           05  GL-FILLER               PIC X(118).

       FD  REPORT-OUTPUT-FILE
           LABEL RECORDS ARE STANDARD.
       01  REPORT-LINE                 PIC X(132).

       FD  ERROR-LOG-FILE
           LABEL RECORDS ARE STANDARD.
       01  ERROR-LOG-RECORD            PIC X(256).

       WORKING-STORAGE SECTION.

      *----------------------------------------------------------------*
      * File status fields                                              *
      *----------------------------------------------------------------*
       01  WS-FILE-STATUSES.
           05  WS-FILE-STATUS-1        PIC X(2) VALUE '00'.
           05  WS-FILE-STATUS-2        PIC X(2) VALUE '00'.
           05  WS-FILE-STATUS-3        PIC X(2) VALUE '00'.
           05  WS-FILE-STATUS-4        PIC X(2) VALUE '00'.
           05  WS-FILE-STATUS-5        PIC X(2) VALUE '00'.
               88  FS-OK               VALUE '00'.
               88  FS-EOF              VALUE '10'.
               88  FS-DUP-KEY          VALUE '22'.
               88  FS-NOT-FOUND        VALUE '23'.

      *----------------------------------------------------------------*
      * Processing date and calendar fields                             *
      *----------------------------------------------------------------*
       01  WS-PROCESSING-DATE.
           05  WS-PROC-YYYY            PIC 9(4).
           05  WS-PROC-MM              PIC 9(2).
           05  WS-PROC-DD              PIC 9(2).

       01  WS-PROC-DATE-NUM            PIC 9(8).
       01  WS-DAYS-IN-MONTH            PIC 9(2).
       01  WS-YEAR-IS-LEAP             PIC X(1).
           88  IS-LEAP-YEAR            VALUE 'Y'.
           88  NOT-LEAP-YEAR           VALUE 'N'.

      *----------------------------------------------------------------*
      * Loan application input record                                   *
      *----------------------------------------------------------------*
       01  WS-LOAN-APPLICATION.
           05  APP-APPLICANT-ID        PIC X(12).
           05  APP-APPLICANT-NAME.
               10  APP-LAST-NAME       PIC X(20).
               10  APP-FIRST-NAME      PIC X(15).
               10  APP-MIDDLE-INIT     PIC X(1).
           05  APP-LOAN-TYPE           PIC X(3).
               88  LOAN-MORTGAGE       VALUE 'MTG'.
               88  LOAN-AUTO           VALUE 'AUT'.
               88  LOAN-PERSONAL       VALUE 'PER'.
               88  LOAN-HELOC          VALUE 'HEL'.
               88  LOAN-COMMERCIAL     VALUE 'COM'.
               88  LOAN-SBA            VALUE 'SBA'.
           05  APP-REQUESTED-AMOUNT    PIC 9(13)V99  COMP-3.
           05  APP-REQUESTED-TERM-MO   PIC 9(3)      COMP.
           05  APP-ANNUAL-INCOME       PIC 9(11)V99  COMP-3.
           05  APP-MONTHLY-OBLIGATIONS PIC 9(9)V99   COMP-3.
           05  APP-CREDIT-SCORE        PIC 9(3).
               88  CREDIT-EXCELLENT    VALUE 750 THRU 850.
               88  CREDIT-GOOD         VALUE 700 THRU 749.
               88  CREDIT-FAIR         VALUE 640 THRU 699.
               88  CREDIT-POOR         VALUE 300 THRU 639.
           05  APP-PROPERTY-VALUE      PIC 9(13)V99  COMP-3.
           05  APP-DOWN-PAYMENT        PIC 9(11)V99  COMP-3.
           05  APP-EMPLOYMENT-TYPE     PIC X(2).
               88  EMP-SALARIED        VALUE 'SA'.
               88  EMP-SELF-EMPLOYED   VALUE 'SE'.
               88  EMP-CONTRACT        VALUE 'CO'.
               88  EMP-RETIRED         VALUE 'RE'.
           05  APP-YEARS-EMPLOYED      PIC 9(2)V9    COMP-3.
           05  APP-EXISTING-LOANS      PIC 9(2)      COMP.
           05  APP-BANKRUPTCY-FLAG     PIC X(1).
               88  HAS-BANKRUPTCY      VALUE 'Y'.
               88  NO-BANKRUPTCY       VALUE 'N'.

      *----------------------------------------------------------------*
      * Credit scoring work area                                        *
      *----------------------------------------------------------------*
       01  WS-CREDIT-SCORING.
           05  CS-BASE-SCORE           PIC 9(4)      COMP.
           05  CS-INCOME-SCORE         PIC 9(4)      COMP.
           05  CS-EMPLOYMENT-SCORE     PIC 9(4)      COMP.
           05  CS-DTI-SCORE            PIC 9(4)      COMP.
           05  CS-LTV-SCORE            PIC 9(4)      COMP.
           05  CS-HISTORY-SCORE        PIC 9(4)      COMP.
           05  CS-TOTAL-SCORE          PIC 9(4)      COMP.
           05  CS-DECISION             PIC X(8).
               88  DECISION-APPROVED   VALUE 'APPROVED'.
               88  DECISION-REFERRED   VALUE 'REFERRED'.
               88  DECISION-DECLINED   VALUE 'DECLINED'.
           05  CS-APPROVED-AMOUNT      PIC 9(13)V99  COMP-3.
           05  CS-APPROVED-RATE        PIC 9(2)V9(6) COMP-3.
           05  CS-APPROVED-TERM        PIC 9(3)      COMP.
           05  CS-RISK-GRADE           PIC X(2).
           05  CS-DECLINE-REASON       PIC X(80).

      *----------------------------------------------------------------*
      * Amortisation calculation fields                                 *
      *----------------------------------------------------------------*
       01  WS-AMORTISATION.
           05  AM-PRINCIPAL            PIC 9(13)V99  COMP-3.
           05  AM-ANNUAL-RATE          PIC 9(2)V9(6) COMP-3.
           05  AM-MONTHLY-RATE         PIC 9(2)V9(8) COMP-3.
           05  AM-TERM-MONTHS          PIC 9(3)      COMP.
           05  AM-MONTHLY-PAYMENT      PIC 9(11)V99  COMP-3.
           05  AM-LOOP-COUNTER         PIC 9(3)      COMP.
           05  AM-INTEREST-PORTION     PIC 9(11)V99  COMP-3.
           05  AM-PRINCIPAL-PORTION    PIC 9(11)V99  COMP-3.
           05  AM-REMAINING-BALANCE    PIC 9(13)V99  COMP-3.
           05  AM-TOTAL-INTEREST       PIC 9(13)V99  COMP-3.
           05  AM-POWER-FACTOR         PIC 9(2)V9(10) COMP-3.
           05  AM-WORK-FIELD-1         PIC 9(15)V99  COMP-3.
           05  AM-WORK-FIELD-2         PIC 9(15)V99  COMP-3.

      *----------------------------------------------------------------*
      * Payment processing work area                                    *
      *----------------------------------------------------------------*
       01  WS-PAYMENT-PROCESSING.
           05  PP-PAYMENT-RECEIVED     PIC 9(11)V99  COMP-3.
           05  PP-AMOUNT-DUE           PIC 9(11)V99  COMP-3.
           05  PP-INTEREST-DUE         PIC 9(11)V99  COMP-3.
           05  PP-PRINCIPAL-DUE        PIC 9(11)V99  COMP-3.
           05  PP-LATE-FEE-DUE         PIC 9(7)V99   COMP-3.
           05  PP-OVERPAYMENT          PIC 9(11)V99  COMP-3.
           05  PP-SHORTFALL            PIC 9(11)V99  COMP-3.
           05  PP-NEW-BALANCE          PIC 9(13)V99  COMP-3.
           05  PP-PAYMENT-STATUS       PIC X(2).
               88  PAY-FULL            VALUE 'FU'.
               88  PAY-PARTIAL         VALUE 'PA'.
               88  PAY-MISSED          VALUE 'MI'.
               88  PAY-EXCESS          VALUE 'EX'.
           05  PP-NSF-FLAG             PIC X(1).
               88  PAYMENT-NSF         VALUE 'Y'.

      *----------------------------------------------------------------*
      * Basel III / Regulatory capital fields                           *
      *----------------------------------------------------------------*
       01  WS-REGULATORY-CAPITAL.
           05  RC-EXPOSURE-AT-DEFAULT  PIC 9(13)V99  COMP-3.
           05  RC-LOSS-GIVEN-DEFAULT   PIC 9(3)V99   COMP-3.
           05  RC-PROB-OF-DEFAULT      PIC 9(1)V9(6) COMP-3.
           05  RC-MATURITY-YEARS       PIC 9(2)V99   COMP-3.
           05  RC-RISK-WEIGHT          PIC 9(3)V99   COMP-3.
           05  RC-RWA-AMOUNT           PIC 9(13)V99  COMP-3.
           05  RC-CAPITAL-REQUIRED     PIC 9(11)V99  COMP-3.
           05  RC-PROVISION-AMOUNT     PIC 9(11)V99  COMP-3.
           05  RC-ECL-STAGE            PIC 9(1).
               88  ECL-STAGE-1         VALUE 1.
               88  ECL-STAGE-2         VALUE 2.
               88  ECL-STAGE-3         VALUE 3.

      *----------------------------------------------------------------*
      * Delinquency management                                          *
      *----------------------------------------------------------------*
       01  WS-DELINQUENCY.
           05  DQ-BUCKET               PIC X(4).
               88  DQ-CURRENT          VALUE 'CUR '.
               88  DQ-30-DAY           VALUE '30  '.
               88  DQ-60-DAY           VALUE '60  '.
               88  DQ-90-DAY           VALUE '90  '.
               88  DQ-120-PLUS         VALUE '120+'.
           05  DQ-COLLECTION-ACTION    PIC X(3).
               88  ACTION-NONE         VALUE 'NON'.
               88  ACTION-LETTER       VALUE 'LET'.
               88  ACTION-CALL         VALUE 'CAL'.
               88  ACTION-LEGAL        VALUE 'LEG'.
               88  ACTION-WRITEOFF     VALUE 'WRO'.
           05  DQ-CURE-PROBABILITY     PIC 9(3)V99   COMP-3.
           05  DQ-DAYS-TO-CHARGE-OFF   PIC 9(3)      COMP.

      *----------------------------------------------------------------*
      * GL posting work area                                            *
      *----------------------------------------------------------------*
       01  WS-GL-WORK.
           05  GL-WORK-JOURNAL-ID      PIC X(20).
           05  GL-LOAN-RECEIVABLE-ACC  PIC X(12) VALUE '1010001000  '.
           05  GL-INTEREST-INCOME-ACC  PIC X(12) VALUE '4010001000  '.
           05  GL-LATE-FEE-ACC         PIC X(12) VALUE '4020001000  '.
           05  GL-PROVISION-EXP-ACC    PIC X(12) VALUE '5010001000  '.
           05  GL-ALLOWANCE-ACC        PIC X(12) VALUE '1019001000  '.
           05  GL-CASH-ACC             PIC X(12) VALUE '1001001000  '.
           05  GL-SUSPENSE-ACC         PIC X(12) VALUE '2099001000  '.

      *----------------------------------------------------------------*
      * Report formatting fields                                        *
      *----------------------------------------------------------------*
       01  WS-REPORT-FIELDS.
           05  RPT-TITLE               PIC X(60).
           05  RPT-PAGE-NO             PIC 9(4)      COMP.
           05  RPT-LINE-COUNT          PIC 9(3)      COMP.
           05  RPT-LOANS-PROCESSED     PIC 9(7)      COMP.
           05  RPT-TOTAL-PRINCIPAL     PIC 9(15)V99  COMP-3.
           05  RPT-TOTAL-INTEREST      PIC 9(13)V99  COMP-3.
           05  RPT-TOTAL-FEES          PIC 9(11)V99  COMP-3.
           05  RPT-TOTAL-RWA           PIC 9(15)V99  COMP-3.
           05  RPT-TOTAL-PROVISIONS    PIC 9(13)V99  COMP-3.

      *----------------------------------------------------------------*
      * General work fields and switches                                *
      *----------------------------------------------------------------*
       01  WS-SWITCHES.
           05  WS-END-OF-FILE          PIC X(1) VALUE 'N'.
               88  END-OF-FILE         VALUE 'Y'.
               88  NOT-END-OF-FILE     VALUE 'N'.
           05  WS-FIRST-PAGE           PIC X(1) VALUE 'Y'.
               88  IS-FIRST-PAGE       VALUE 'Y'.
           05  WS-ERRORS-FOUND         PIC X(1) VALUE 'N'.
               88  ERRORS-FOUND        VALUE 'Y'.
           05  WS-POSTING-ACTIVE       PIC X(1) VALUE 'N'.

       01  WS-COUNTERS.
           05  WS-RECORDS-READ         PIC 9(9)  COMP VALUE ZEROS.
           05  WS-RECORDS-WRITTEN      PIC 9(9)  COMP VALUE ZEROS.
           05  WS-RECORDS-ERRORED      PIC 9(9)  COMP VALUE ZEROS.
           05  WS-LOOP-IDX             PIC 9(4)  COMP VALUE ZEROS.
           05  WS-RETRY-COUNT          PIC 9(2)  COMP VALUE ZEROS.
           05  WS-MAX-RETRIES          PIC 9(2)  COMP VALUE 3.

       01  WS-WORK-FIELDS.
           05  WS-RETURN-CODE          PIC 9(4) VALUE ZEROS.
               88  RC-SUCCESS          VALUE 0.
               88  RC-WARNING          VALUE 4.
               88  RC-ERROR            VALUE 8.
               88  RC-FATAL            VALUE 12.
           05  WS-ERROR-CODE           PIC X(8).
           05  WS-ERROR-MSG            PIC X(120).
           05  WS-TEMP-AMOUNT          PIC 9(13)V99  COMP-3.
           05  WS-TEMP-RATE            PIC 9(4)V9(8) COMP-3.
           05  WS-TEMP-NUMERIC         PIC 9(12)     COMP.
           05  WS-NUMERIC-WORK         PIC 9(18)V99  COMP-3.
           05  WS-FORMATTED-AMT        PIC $ZZZ,ZZZ,ZZZ,ZZ9.99.
           05  WS-FORMATTED-DATE       PIC X(10).
           05  WS-CURRENT-TIMESTAMP    PIC X(26).

       01  WS-CONSTANTS.
           05  C-DAYS-PER-YEAR         PIC 9(3)  VALUE 365.
           05  C-MONTHS-PER-YEAR       PIC 9(2)  VALUE 12.
           05  C-CAPITAL-RATIO         PIC 9(2)V99 VALUE 8.00.
           05  C-LATE-FEE-FLAT         PIC 9(5)V99 VALUE 35.00.
           05  C-LATE-FEE-PCT          PIC 9(1)V99 VALUE 5.00.
           05  C-NSF-FEE               PIC 9(5)V99 VALUE 25.00.
           05  C-MAX-DTI-RATIO         PIC 9(2)V99 VALUE 43.00.
           05  C-MIN-DOWN-PAYMENT-PCT  PIC 9(2)V99 VALUE 3.50.
           05  C-PRIME-RATE            PIC 9(2)V9(4) VALUE 8.500000.
           05  C-LINES-PER-PAGE        PIC 9(3)  VALUE 60.

       PROCEDURE DIVISION.

      *================================================================*
       MAIN-PROCESS.
           PERFORM PROGRAM-INITIALIZATION.
           PERFORM OPEN-ALL-FILES.
           PERFORM PROCESS-LOAN-PORTFOLIO
               UNTIL END-OF-FILE.
           PERFORM GENERATE-REGULATORY-REPORT.
           PERFORM CLOSE-ALL-FILES.
           PERFORM PROGRAM-TERMINATION.
           STOP RUN.

      *================================================================*
       PROGRAM-INITIALIZATION.
           MOVE ZEROS TO WS-COUNTERS.
           MOVE ZEROS TO WS-RETURN-CODE.
           MOVE ZEROS TO RPT-LOANS-PROCESSED.
           MOVE ZEROS TO RPT-TOTAL-PRINCIPAL.
           MOVE ZEROS TO RPT-TOTAL-INTEREST.
           MOVE ZEROS TO RPT-TOTAL-FEES.
           MOVE ZEROS TO RPT-TOTAL-RWA.
           MOVE ZEROS TO RPT-TOTAL-PROVISIONS.
           MOVE 1 TO RPT-PAGE-NO.
           MOVE 0 TO RPT-LINE-COUNT.
           MOVE 'N' TO WS-END-OF-FILE.
           MOVE 'Y' TO WS-FIRST-PAGE.
           MOVE 'N' TO WS-ERRORS-FOUND.
           ACCEPT WS-PROC-DATE-NUM FROM DATE YYYYMMDD.
           MOVE WS-PROC-DATE-NUM(1:4) TO WS-PROC-YYYY.
           MOVE WS-PROC-DATE-NUM(5:2) TO WS-PROC-MM.
           MOVE WS-PROC-DATE-NUM(7:2) TO WS-PROC-DD.
           PERFORM DETERMINE-LEAP-YEAR.

      *================================================================*
       DETERMINE-LEAP-YEAR.
           EVALUATE TRUE
               WHEN FUNCTION MOD(WS-PROC-YYYY, 400) = 0
                   MOVE 'Y' TO WS-YEAR-IS-LEAP
               WHEN FUNCTION MOD(WS-PROC-YYYY, 100) = 0
                   MOVE 'N' TO WS-YEAR-IS-LEAP
               WHEN FUNCTION MOD(WS-PROC-YYYY, 4) = 0
                   MOVE 'Y' TO WS-YEAR-IS-LEAP
               WHEN OTHER
                   MOVE 'N' TO WS-YEAR-IS-LEAP
           END-EVALUATE.
           IF IS-LEAP-YEAR
               MOVE 366 TO C-DAYS-PER-YEAR
           ELSE
               MOVE 365 TO C-DAYS-PER-YEAR
           END-IF.

      *================================================================*
       OPEN-ALL-FILES.
           OPEN INPUT  LOAN-MASTER-FILE.
           IF WS-FILE-STATUS-1 NOT = '00'
               MOVE 'LOAN-MASTER-FILE OPEN FAILED' TO WS-ERROR-MSG
               MOVE 12 TO WS-RETURN-CODE
               PERFORM LOG-FATAL-ERROR
           END-IF.
           OPEN INPUT  PAYMENT-HISTORY-FILE.
           OPEN OUTPUT GL-POSTING-FILE.
           OPEN OUTPUT REPORT-OUTPUT-FILE.
           OPEN OUTPUT ERROR-LOG-FILE.

      *================================================================*
       PROCESS-LOAN-PORTFOLIO.
           READ LOAN-MASTER-FILE NEXT RECORD
               AT END MOVE 'Y' TO WS-END-OF-FILE
               NOT AT END
                   ADD 1 TO WS-RECORDS-READ
                   PERFORM PROCESS-SINGLE-LOAN
           END-READ.

      *================================================================*
       PROCESS-SINGLE-LOAN.
           PERFORM VALIDATE-LOAN-RECORD.
           IF RC-SUCCESS
               PERFORM CALCULATE-LOAN-METRICS
               PERFORM CLASSIFY-DELINQUENCY
               PERFORM CALCULATE-REGULATORY-CAPITAL
               PERFORM CALCULATE-LOSS-PROVISION
               PERFORM DETERMINE-COLLECTION-ACTION
               PERFORM POST-GL-ENTRIES
               PERFORM UPDATE-REPORT-TOTALS
               ADD 1 TO RPT-LOANS-PROCESSED
               ADD 1 TO WS-RECORDS-WRITTEN
           ELSE
               ADD 1 TO WS-RECORDS-ERRORED
               PERFORM LOG-PROCESSING-ERROR
           END-IF.

      *================================================================*
       VALIDATE-LOAN-RECORD.
           MOVE 0 TO WS-RETURN-CODE.
           MOVE SPACES TO WS-ERROR-MSG.
           IF LM-LOAN-ID = SPACES OR LOW-VALUES
               MOVE 8 TO WS-RETURN-CODE
               MOVE 'INVALID LOAN ID' TO WS-ERROR-MSG
               EXIT PARAGRAPH
           END-IF.
           IF LM-PRINCIPAL <= ZEROS
               MOVE 8 TO WS-RETURN-CODE
               MOVE 'PRINCIPAL AMOUNT INVALID' TO WS-ERROR-MSG
               EXIT PARAGRAPH
           END-IF.
           IF LM-INTEREST-RATE <= ZEROS OR LM-INTEREST-RATE > 50
               MOVE 8 TO WS-RETURN-CODE
               MOVE 'INTEREST RATE OUT OF RANGE' TO WS-ERROR-MSG
               EXIT PARAGRAPH
           END-IF.
           IF LM-CREDIT-SCORE < 300 OR LM-CREDIT-SCORE > 850
               MOVE 4 TO WS-RETURN-CODE
               MOVE 'CREDIT SCORE OUT OF RANGE - WARNING' TO WS-ERROR-MSG
           END-IF.

      *================================================================*
       CALCULATE-LOAN-METRICS.
           PERFORM CALCULATE-DAYS-IN-MONTH.
           COMPUTE AM-MONTHLY-RATE =
               LM-INTEREST-RATE / C-MONTHS-PER-YEAR / 100.
           MOVE LM-OUTSTANDING-BAL TO AM-REMAINING-BALANCE.
           MOVE LM-PRINCIPAL TO AM-PRINCIPAL.
           MOVE LM-INTEREST-RATE TO AM-ANNUAL-RATE.
           PERFORM CALCULATE-MONTHLY-PAYMENT.

      *================================================================*
       CALCULATE-DAYS-IN-MONTH.
           EVALUATE WS-PROC-MM
               WHEN 1 WHEN 3 WHEN 5 WHEN 7
               WHEN 8 WHEN 10 WHEN 12
                   MOVE 31 TO WS-DAYS-IN-MONTH
               WHEN 4 WHEN 6 WHEN 9 WHEN 11
                   MOVE 30 TO WS-DAYS-IN-MONTH
               WHEN 2
                   IF IS-LEAP-YEAR
                       MOVE 29 TO WS-DAYS-IN-MONTH
                   ELSE
                       MOVE 28 TO WS-DAYS-IN-MONTH
                   END-IF
               WHEN OTHER
                   MOVE 30 TO WS-DAYS-IN-MONTH
           END-EVALUATE.

      *================================================================*
       CALCULATE-MONTHLY-PAYMENT.
           IF AM-MONTHLY-RATE = ZEROS
               COMPUTE AM-MONTHLY-PAYMENT =
                   AM-PRINCIPAL / LM-OUTSTANDING-BAL
           ELSE
               COMPUTE AM-POWER-FACTOR =
                   (1 + AM-MONTHLY-RATE) ** AM-TERM-MONTHS
               COMPUTE AM-WORK-FIELD-1 =
                   AM-PRINCIPAL * AM-MONTHLY-RATE * AM-POWER-FACTOR
               COMPUTE AM-WORK-FIELD-2 =
                   AM-POWER-FACTOR - 1
               IF AM-WORK-FIELD-2 > ZEROS
                   COMPUTE AM-MONTHLY-PAYMENT =
                       AM-WORK-FIELD-1 / AM-WORK-FIELD-2
               ELSE
                   MOVE LM-MONTHLY-PAYMENT TO AM-MONTHLY-PAYMENT
               END-IF
           END-IF.
           MOVE 0 TO AM-TOTAL-INTEREST.
           MOVE AM-REMAINING-BALANCE TO AM-WORK-FIELD-1.
           PERFORM VARYING AM-LOOP-COUNTER FROM 1 BY 1
               UNTIL AM-LOOP-COUNTER > 360
                   OR AM-WORK-FIELD-1 <= ZEROS
               COMPUTE AM-INTEREST-PORTION =
                   AM-WORK-FIELD-1 * AM-MONTHLY-RATE
               COMPUTE AM-PRINCIPAL-PORTION =
                   AM-MONTHLY-PAYMENT - AM-INTEREST-PORTION
               IF AM-PRINCIPAL-PORTION > AM-WORK-FIELD-1
                   MOVE AM-WORK-FIELD-1 TO AM-PRINCIPAL-PORTION
               END-IF
               ADD AM-INTEREST-PORTION TO AM-TOTAL-INTEREST
               SUBTRACT AM-PRINCIPAL-PORTION FROM AM-WORK-FIELD-1
           END-PERFORM.

      *================================================================*
       CLASSIFY-DELINQUENCY.
           EVALUATE TRUE
               WHEN LM-DAYS-PAST-DUE = 0
                   MOVE 'CUR ' TO DQ-BUCKET
                   MOVE 1 TO RC-ECL-STAGE
               WHEN LM-DAYS-PAST-DUE <= 30
                   MOVE '30  ' TO DQ-BUCKET
                   MOVE 1 TO RC-ECL-STAGE
               WHEN LM-DAYS-PAST-DUE <= 60
                   MOVE '60  ' TO DQ-BUCKET
                   MOVE 2 TO RC-ECL-STAGE
               WHEN LM-DAYS-PAST-DUE <= 90
                   MOVE '90  ' TO DQ-BUCKET
                   MOVE 2 TO RC-ECL-STAGE
               WHEN OTHER
                   MOVE '120+' TO DQ-BUCKET
                   MOVE 3 TO RC-ECL-STAGE
           END-EVALUATE.
           PERFORM ASSESS-CURE-PROBABILITY.

      *================================================================*
       ASSESS-CURE-PROBABILITY.
           EVALUATE TRUE
               WHEN DQ-CURRENT
                   MOVE 99.50 TO DQ-CURE-PROBABILITY
                   MOVE 0 TO DQ-DAYS-TO-CHARGE-OFF
               WHEN DQ-30-DAY
                   IF LM-CREDIT-SCORE >= 700
                       MOVE 85.00 TO DQ-CURE-PROBABILITY
                   ELSE
                       MOVE 65.00 TO DQ-CURE-PROBABILITY
                   END-IF
                   MOVE 150 TO DQ-DAYS-TO-CHARGE-OFF
               WHEN DQ-60-DAY
                   IF LM-CREDIT-SCORE >= 650
                       MOVE 55.00 TO DQ-CURE-PROBABILITY
                   ELSE
                       MOVE 30.00 TO DQ-CURE-PROBABILITY
                   END-IF
                   MOVE 120 TO DQ-DAYS-TO-CHARGE-OFF
               WHEN DQ-90-DAY
                   COMPUTE DQ-CURE-PROBABILITY =
                       LM-CREDIT-SCORE * 0.02
                   MOVE 90 TO DQ-DAYS-TO-CHARGE-OFF
               WHEN DQ-120-PLUS
                   MOVE 5.00 TO DQ-CURE-PROBABILITY
                   MOVE 30 TO DQ-DAYS-TO-CHARGE-OFF
           END-EVALUATE.

      *================================================================*
       CALCULATE-REGULATORY-CAPITAL.
           MOVE LM-OUTSTANDING-BAL TO RC-EXPOSURE-AT-DEFAULT.
           PERFORM ASSIGN-RISK-WEIGHT.
           COMPUTE RC-RWA-AMOUNT =
               RC-EXPOSURE-AT-DEFAULT * RC-RISK-WEIGHT / 100.
           COMPUTE RC-CAPITAL-REQUIRED =
               RC-RWA-AMOUNT * C-CAPITAL-RATIO / 100.
           MOVE RC-RISK-WEIGHT TO LM-RWA-WEIGHT.

      *================================================================*
       ASSIGN-RISK-WEIGHT.
           EVALUATE TRUE
               WHEN LOAN-MORTGAGE
                   IF LM-LTV-RATIO <= 80
                       MOVE 35.00 TO RC-RISK-WEIGHT
                   ELSE IF LM-LTV-RATIO <= 90
                       MOVE 50.00 TO RC-RISK-WEIGHT
                   ELSE
                       MOVE 100.00 TO RC-RISK-WEIGHT
                   END-IF
               WHEN LOAN-COMMERCIAL
                   EVALUATE LM-RISK-GRADE
                       WHEN 'AA' WHEN 'A1'
                           MOVE 20.00 TO RC-RISK-WEIGHT
                       WHEN 'A2' WHEN 'BB'
                           MOVE 50.00 TO RC-RISK-WEIGHT
                       WHEN 'B1' WHEN 'B2'
                           MOVE 100.00 TO RC-RISK-WEIGHT
                       WHEN OTHER
                           MOVE 150.00 TO RC-RISK-WEIGHT
                   END-EVALUATE
               WHEN LOAN-PERSONAL WHEN LOAN-AUTO
                   MOVE 75.00 TO RC-RISK-WEIGHT
               WHEN OTHER
                   MOVE 100.00 TO RC-RISK-WEIGHT
           END-EVALUATE.
           IF ECL-STAGE-3
               COMPUTE RC-RISK-WEIGHT = RC-RISK-WEIGHT * 1.25
           END-IF.

      *================================================================*
       CALCULATE-LOSS-PROVISION.
           EVALUATE TRUE
               WHEN ECL-STAGE-1
                   COMPUTE RC-PROB-OF-DEFAULT =
                       (850 - LM-CREDIT-SCORE) * 0.000200
                   COMPUTE RC-LOSS-GIVEN-DEFAULT =
                       LM-LTV-RATIO * 0.45
                   COMPUTE LM-PROVISION-PCT =
                       RC-PROB-OF-DEFAULT * RC-LOSS-GIVEN-DEFAULT / 100
               WHEN ECL-STAGE-2
                   COMPUTE RC-PROB-OF-DEFAULT =
                       (850 - LM-CREDIT-SCORE) * 0.000800
                   COMPUTE RC-LOSS-GIVEN-DEFAULT =
                       LM-LTV-RATIO * 0.55
                   COMPUTE LM-PROVISION-PCT =
                       RC-PROB-OF-DEFAULT * RC-LOSS-GIVEN-DEFAULT / 100
               WHEN ECL-STAGE-3
                   MOVE 1.000000 TO RC-PROB-OF-DEFAULT
                   COMPUTE RC-LOSS-GIVEN-DEFAULT =
                       LM-LTV-RATIO * 0.70
                   COMPUTE LM-PROVISION-PCT =
                       RC-LOSS-GIVEN-DEFAULT / 100
           END-EVALUATE.
           COMPUTE RC-PROVISION-AMOUNT =
               LM-OUTSTANDING-BAL * LM-PROVISION-PCT.

      *================================================================*
       DETERMINE-COLLECTION-ACTION.
           EVALUATE TRUE
               WHEN DQ-CURRENT
                   MOVE 'NON' TO DQ-COLLECTION-ACTION
               WHEN DQ-30-DAY
                   MOVE 'LET' TO DQ-COLLECTION-ACTION
                   PERFORM GENERATE-COLLECTION-LETTER
               WHEN DQ-60-DAY
                   IF DQ-CURE-PROBABILITY > 40
                       MOVE 'CAL' TO DQ-COLLECTION-ACTION
                   ELSE
                       MOVE 'LEG' TO DQ-COLLECTION-ACTION
                   END-IF
               WHEN DQ-90-DAY
                   MOVE 'LEG' TO DQ-COLLECTION-ACTION
                   PERFORM INITIATE-LEGAL-PROCEEDINGS
               WHEN DQ-120-PLUS
                   IF LM-COLLATERAL-VALUE > ZEROS
                       PERFORM INITIATE-COLLATERAL-RECOVERY
                   ELSE
                       MOVE 'WRO' TO DQ-COLLECTION-ACTION
                       PERFORM PROCESS-CHARGE-OFF
                   END-IF
           END-EVALUATE.

      *================================================================*
       GENERATE-COLLECTION-LETTER.
           MOVE 'COLLECTION LETTER QUEUED' TO WS-ERROR-MSG.
           ADD 1 TO WS-RECORDS-WRITTEN.

      *================================================================*
       INITIATE-LEGAL-PROCEEDINGS.
           MOVE 'LEG' TO DQ-COLLECTION-ACTION.
           MOVE 'LEGAL PROCEEDINGS INITIATED' TO WS-ERROR-MSG.

      *================================================================*
       INITIATE-COLLATERAL-RECOVERY.
           MOVE 'COLLATERAL RECOVERY INITIATED' TO WS-ERROR-MSG.

      *================================================================*
       PROCESS-CHARGE-OFF.
           MOVE 'CHARGE-OFF PROCESSED' TO WS-ERROR-MSG.
           MOVE 'CO' TO LM-STATUS.

      *================================================================*
       POST-GL-ENTRIES.
           PERFORM POST-PRINCIPAL-GL.
           PERFORM POST-INTEREST-GL.
           IF RC-PROVISION-AMOUNT > ZEROS
               PERFORM POST-PROVISION-GL
           END-IF.
           IF LM-DAYS-PAST-DUE > 0
               PERFORM POST-LATE-FEE-GL
           END-IF.

      *================================================================*
       POST-PRINCIPAL-GL.
           MOVE LM-LOAN-ID TO GL-WORK-JOURNAL-ID.
           MOVE GL-LOAN-RECEIVABLE-ACC TO GL-ACCOUNT-CODE.
           MOVE LM-OUTSTANDING-BAL TO GL-DEBIT-AMOUNT.
           MOVE ZEROS TO GL-CREDIT-AMOUNT.
           MOVE 'LOAN RECEIVABLE BALANCE' TO GL-DESCRIPTION.
           MOVE WS-PROC-DATE-NUM TO GL-POSTING-DATE.
           MOVE 'CAD' TO GL-CURRENCY.
           WRITE GL-POSTING-RECORD.

      *================================================================*
       POST-INTEREST-GL.
           COMPUTE WS-TEMP-AMOUNT =
               LM-OUTSTANDING-BAL * LM-INTEREST-RATE / 100
               / C-MONTHS-PER-YEAR.
           MOVE GL-INTEREST-INCOME-ACC TO GL-ACCOUNT-CODE.
           MOVE ZEROS TO GL-DEBIT-AMOUNT.
           MOVE WS-TEMP-AMOUNT TO GL-CREDIT-AMOUNT.
           MOVE 'INTEREST INCOME ACCRUAL' TO GL-DESCRIPTION.
           WRITE GL-POSTING-RECORD.

      *================================================================*
       POST-PROVISION-GL.
           MOVE GL-PROVISION-EXP-ACC TO GL-ACCOUNT-CODE.
           MOVE RC-PROVISION-AMOUNT TO GL-DEBIT-AMOUNT.
           MOVE ZEROS TO GL-CREDIT-AMOUNT.
           MOVE 'ECL PROVISION EXPENSE' TO GL-DESCRIPTION.
           WRITE GL-POSTING-RECORD.
           MOVE GL-ALLOWANCE-ACC TO GL-ACCOUNT-CODE.
           MOVE ZEROS TO GL-DEBIT-AMOUNT.
           MOVE RC-PROVISION-AMOUNT TO GL-CREDIT-AMOUNT.
           MOVE 'ALLOWANCE FOR CREDIT LOSSES' TO GL-DESCRIPTION.
           WRITE GL-POSTING-RECORD.

      *================================================================*
       POST-LATE-FEE-GL.
           COMPUTE PP-LATE-FEE-DUE =
               FUNCTION MAX(C-LATE-FEE-FLAT,
                   LM-OUTSTANDING-BAL * C-LATE-FEE-PCT / 100).
           MOVE GL-LATE-FEE-ACC TO GL-ACCOUNT-CODE.
           MOVE ZEROS TO GL-DEBIT-AMOUNT.
           MOVE PP-LATE-FEE-DUE TO GL-CREDIT-AMOUNT.
           MOVE 'LATE FEE INCOME' TO GL-DESCRIPTION.
           WRITE GL-POSTING-RECORD.
           ADD PP-LATE-FEE-DUE TO RPT-TOTAL-FEES.

      *================================================================*
       UPDATE-REPORT-TOTALS.
           ADD LM-PRINCIPAL        TO RPT-TOTAL-PRINCIPAL.
           ADD AM-TOTAL-INTEREST   TO RPT-TOTAL-INTEREST.
           ADD RC-RWA-AMOUNT       TO RPT-TOTAL-RWA.
           ADD RC-PROVISION-AMOUNT TO RPT-TOTAL-PROVISIONS.

      *================================================================*
       GENERATE-REGULATORY-REPORT.
           PERFORM WRITE-REPORT-HEADER.
           PERFORM WRITE-PORTFOLIO-SUMMARY.
           PERFORM WRITE-BASEL-SUMMARY.
           PERFORM WRITE-DELINQUENCY-SUMMARY.
           PERFORM WRITE-REPORT-FOOTER.

      *================================================================*
       WRITE-REPORT-HEADER.
           MOVE SPACES TO REPORT-LINE.
           STRING 'LOAN PORTFOLIO REGULATORY REPORT'
                  '  DATE: ' WS-PROC-DATE-NUM
               DELIMITED SIZE INTO REPORT-LINE.
           WRITE REPORT-LINE.
           MOVE ALL '-' TO REPORT-LINE.
           WRITE REPORT-LINE.

      *================================================================*
       WRITE-PORTFOLIO-SUMMARY.
           MOVE SPACES TO REPORT-LINE.
           STRING 'TOTAL LOANS PROCESSED: '
                  RPT-LOANS-PROCESSED
               DELIMITED SIZE INTO REPORT-LINE.
           WRITE REPORT-LINE.
           MOVE RPT-TOTAL-PRINCIPAL TO WS-FORMATTED-AMT.
           MOVE SPACES TO REPORT-LINE.
           STRING 'TOTAL PRINCIPAL OUTSTANDING: '
                  WS-FORMATTED-AMT
               DELIMITED SIZE INTO REPORT-LINE.
           WRITE REPORT-LINE.

      *================================================================*
       WRITE-BASEL-SUMMARY.
           MOVE RPT-TOTAL-RWA TO WS-FORMATTED-AMT.
           MOVE SPACES TO REPORT-LINE.
           STRING 'TOTAL RISK-WEIGHTED ASSETS: '
                  WS-FORMATTED-AMT
               DELIMITED SIZE INTO REPORT-LINE.
           WRITE REPORT-LINE.
           MOVE RPT-TOTAL-PROVISIONS TO WS-FORMATTED-AMT.
           MOVE SPACES TO REPORT-LINE.
           STRING 'TOTAL ECL PROVISIONS: '
                  WS-FORMATTED-AMT
               DELIMITED SIZE INTO REPORT-LINE.
           WRITE REPORT-LINE.

      *================================================================*
       WRITE-DELINQUENCY-SUMMARY.
           MOVE SPACES TO REPORT-LINE.
           MOVE 'DELINQUENCY BREAKDOWN BY BUCKET' TO REPORT-LINE.
           WRITE REPORT-LINE.

      *================================================================*
       WRITE-REPORT-FOOTER.
           MOVE ALL '=' TO REPORT-LINE.
           WRITE REPORT-LINE.
           MOVE SPACES TO REPORT-LINE.
           STRING 'END OF REPORT  PAGE: ' RPT-PAGE-NO
               DELIMITED SIZE INTO REPORT-LINE.
           WRITE REPORT-LINE.

      *================================================================*
       CLOSE-ALL-FILES.
           CLOSE LOAN-MASTER-FILE.
           CLOSE PAYMENT-HISTORY-FILE.
           CLOSE GL-POSTING-FILE.
           CLOSE REPORT-OUTPUT-FILE.
           CLOSE ERROR-LOG-FILE.

      *================================================================*
       LOG-FATAL-ERROR.
           MOVE 'Y' TO WS-ERRORS-FOUND.
           MOVE WS-ERROR-MSG TO ERROR-LOG-RECORD.
           WRITE ERROR-LOG-RECORD.
           STOP RUN.

      *================================================================*
       LOG-PROCESSING-ERROR.
           MOVE 'Y' TO WS-ERRORS-FOUND.
           MOVE WS-ERROR-MSG TO ERROR-LOG-RECORD.
           WRITE ERROR-LOG-RECORD.

      *================================================================*
       PROGRAM-TERMINATION.
           IF ERRORS-FOUND
               MOVE 4 TO WS-RETURN-CODE
           END-IF.
           MOVE WS-RETURN-CODE TO RETURN-CODE.