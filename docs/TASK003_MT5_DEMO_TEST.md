# XAUPY Task 003 — MT5 Demo Smoke Test

Use a demo MT5 account only.

1. Extract the full Task 003 ZIP.
2. Run XAUPY.Desktop.exe and wait for Python Engine READY.
3. In MT5, open Tools → Options → Expert Advisors.
4. Enable the allowed URL list and add http://127.0.0.1:39421.
5. Open File → Open Data Folder.
6. Copy mt5/XAUPY_Bridge_EA.ex5 into MQL5/Experts.
7. Refresh Navigator or restart MT5.
8. Attach XAUPY_Bridge_EA to the XAUUSD chart.
9. Keep Algo Trading enabled only so MQL can use normal EA permissions; Task 003 still has no order execution code.
10. Expected XAUPY Desktop result:
    - Python Engine: READY
    - MT5 Bridge: CONNECTED
    - symbol visible
    - guardian: EXECUTION LOCKED
    - heartbeat/snapshot age continuously refreshes
11. Detach the EA. Within roughly five seconds the Desktop should show MT5 Bridge WAITING/OFFLINE.
12. Reattach the EA. The Bridge should return to CONNECTED automatically.

Task 003 must never place, modify or close an order.
