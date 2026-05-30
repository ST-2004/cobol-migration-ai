       IDENTIFICATION DIVISION.
       PROGRAM-ID. PAYROLL-CALC.
       AUTHOR. COBOL-MIGRATION-AI.

       DATA DIVISION.
       WORKING-STORAGE SECTION.

       01 WS-EMPLOYEE-RECORD.
          05 WS-EMP-ID          PIC X(8).
          05 WS-EMP-NAME        PIC X(30).
          05 WS-DEPT-CODE       PIC XX.
          05 WS-HOURS-WORKED    PIC 9(3)V9  COMP-3.
          05 WS-HOURLY-RATE     PIC 9(5)V99 COMP-3.
          05 WS-GROSS-PAY       PIC 9(7)V99 COMP-3.
          05 WS-TAX-AMOUNT      PIC 9(6)V99 COMP-3.
          05 WS-NET-PAY         PIC 9(7)V99 COMP-3.
          05 WS-OVERTIME-HRS    PIC 9(3)V9  COMP-3.
          05 WS-OVERTIME-PAY    PIC 9(6)V99 COMP-3.

       01 WS-TAX-BRACKETS.
          05 WS-TAX-RATE-LOW    PIC 9V99    VALUE 0.15.
          05 WS-TAX-RATE-MID    PIC 9V99    VALUE 0.25.
          05 WS-TAX-RATE-HIGH   PIC 9V99    VALUE 0.33.
          05 WS-BRACKET-1-LIMIT PIC 9(6)V99 VALUE 50000.00.
          05 WS-BRACKET-2-LIMIT PIC 9(6)V99 VALUE 100000.00.

       01 WS-COUNTERS.
          05 WS-RECORDS-IN      PIC 9(5) VALUE ZERO.
          05 WS-RECORDS-OUT     PIC 9(5) VALUE ZERO.
          05 WS-ERROR-COUNT     PIC 9(3) VALUE ZERO.

       01 WS-FLAGS.
          05 WS-VALID-FLAG      PIC X    VALUE 'Y'.
             88 RECORD-VALID              VALUE 'Y'.
             88 RECORD-INVALID            VALUE 'N'.
          05 WS-OVERTIME-FLAG   PIC X    VALUE 'N'.
             88 HAS-OVERTIME              VALUE 'Y'.
             88 NO-OVERTIME               VALUE 'N'.

       01 WS-CONSTANTS.
          05 WS-STD-HOURS       PIC 9(3) VALUE 40.
          05 WS-OT-MULTIPLIER   PIC 9V9  VALUE 1.5.
          05 WS-MAX-HOURS       PIC 9(3) VALUE 80.

       01 WS-RETURN-CODE        PIC 99   VALUE ZERO.
       01 WS-ERROR-MSG          PIC X(50) VALUE SPACES.
       01 WS-ANNUAL-GROSS       PIC 9(8)V99 COMP-3.

       PROCEDURE DIVISION.

       MAIN-PARA.
           PERFORM INITIALISE-PARA.
           PERFORM PROCESS-EMPLOYEE-PARA.
           PERFORM COMPUTE-TAX-PARA.
           PERFORM COMPUTE-NET-PARA.
           PERFORM VALIDATE-OUTPUT-PARA.
           PERFORM DISPLAY-RESULTS-PARA.
           STOP RUN.

       INITIALISE-PARA.
           MOVE ZEROS TO WS-GROSS-PAY
                         WS-TAX-AMOUNT
                         WS-NET-PAY
                         WS-OVERTIME-PAY
                         WS-OVERTIME-HRS.
           MOVE 'Y' TO WS-VALID-FLAG.
           MOVE 'N' TO WS-OVERTIME-FLAG.
           MOVE SPACES TO WS-ERROR-MSG.
           ADD 1 TO WS-RECORDS-IN.

       PROCESS-EMPLOYEE-PARA.
           IF WS-HOURS-WORKED > WS-MAX-HOURS
               MOVE 'N' TO WS-VALID-FLAG
               MOVE 'HOURS EXCEED MAXIMUM ALLOWED' TO WS-ERROR-MSG
               ADD 1 TO WS-ERROR-COUNT
           ELSE
               IF WS-HOURLY-RATE <= ZERO
                   MOVE 'N' TO WS-VALID-FLAG
                   MOVE 'INVALID HOURLY RATE' TO WS-ERROR-MSG
                   ADD 1 TO WS-ERROR-COUNT
               END-IF
           END-IF.
           IF RECORD-VALID
               PERFORM COMPUTE-GROSS-PARA
           END-IF.

       COMPUTE-GROSS-PARA.
           IF WS-HOURS-WORKED > WS-STD-HOURS
               MOVE 'Y' TO WS-OVERTIME-FLAG
               SUBTRACT WS-STD-HOURS FROM WS-HOURS-WORKED
                   GIVING WS-OVERTIME-HRS
               COMPUTE WS-OVERTIME-PAY =
                   WS-OVERTIME-HRS * WS-HOURLY-RATE * WS-OT-MULTIPLIER
               COMPUTE WS-GROSS-PAY =
                   (WS-STD-HOURS * WS-HOURLY-RATE) + WS-OVERTIME-PAY
           ELSE
               COMPUTE WS-GROSS-PAY =
                   WS-HOURS-WORKED * WS-HOURLY-RATE
           END-IF.

       COMPUTE-TAX-PARA.
           COMPUTE WS-ANNUAL-GROSS = WS-GROSS-PAY * 26.
           EVALUATE TRUE
               WHEN WS-ANNUAL-GROSS <= WS-BRACKET-1-LIMIT
                   COMPUTE WS-TAX-AMOUNT =
                       WS-GROSS-PAY * WS-TAX-RATE-LOW
               WHEN WS-ANNUAL-GROSS <= WS-BRACKET-2-LIMIT
                   COMPUTE WS-TAX-AMOUNT =
                       WS-GROSS-PAY * WS-TAX-RATE-MID
               WHEN OTHER
                   COMPUTE WS-TAX-AMOUNT =
                       WS-GROSS-PAY * WS-TAX-RATE-HIGH
           END-EVALUATE.

       COMPUTE-NET-PARA.
           SUBTRACT WS-TAX-AMOUNT FROM WS-GROSS-PAY
               GIVING WS-NET-PAY.
           IF WS-NET-PAY < ZERO
               MOVE ZERO TO WS-NET-PAY
               MOVE 'N' TO WS-VALID-FLAG
               MOVE 'NET PAY NEGATIVE - CHECK RATES' TO WS-ERROR-MSG
           END-IF.

       VALIDATE-OUTPUT-PARA.
           IF RECORD-VALID
               ADD 1 TO WS-RECORDS-OUT
               MOVE WS-RETURN-CODE TO WS-RETURN-CODE
           ELSE
               DISPLAY 'ERROR: ' WS-ERROR-MSG
           END-IF.

       DISPLAY-RESULTS-PARA.
           DISPLAY 'EMPLOYEE : ' WS-EMP-NAME.
           DISPLAY 'DEPT     : ' WS-DEPT-CODE.
           DISPLAY 'GROSS PAY: ' WS-GROSS-PAY.
           DISPLAY 'TAX      : ' WS-TAX-AMOUNT.
           DISPLAY 'NET PAY  : ' WS-NET-PAY.
           IF HAS-OVERTIME
               DISPLAY 'OVERTIME : ' WS-OVERTIME-PAY
           END-IF.
           DISPLAY 'RECORDS IN : ' WS-RECORDS-IN.
           DISPLAY 'RECORDS OUT: ' WS-RECORDS-OUT.
           DISPLAY 'ERRORS     : ' WS-ERROR-COUNT.
